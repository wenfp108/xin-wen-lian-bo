#!/usr/bin/env python3
"""
新闻联播政策信号分析器（v2）

相比 v1 的改动：
1. 最长匹配优先（正则交替按词长排序）——「新能源汽车」不再同时计入「汽车」「能源」
2. 否定语境识别——「防范房地产风险」记入 negative，而不是房地产热度
3. 以「提及该行业的新闻条数 / 当日总条数」作为注意力指标，不再被长稿和低基数放大
4. 30 日滚动 z-score + 7 日 EMA，输出「异常度」而不只是绝对分数
5. 关键词过滤数字/泛政治词，jieba 缺失时自动降级
6. 保留 v1 的输出字段（sector_scores / top_keywords / items），新增字段向后兼容

用法：
    python policy_nlp.py run                 # 分析最新一天
    python policy_nlp.py date 20261006       # 分析指定日期
    python policy_nlp.py all                 # 批量处理全部新闻
    python policy_nlp.py trends 7            # 最近 N 天趋势
    python policy_nlp.py report 20261006     # 打印 Markdown 报告

有 GH_PAT 时结果推送到 Central-Bank；没有则写入本地 results/。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ---------- 可选依赖 ----------
try:
    import jieba
    import jieba.analyse
except ImportError:  # 没有 jieba 也能跑，关键词降级为词频
    jieba = None

try:
    from github import Github, Auth
except ImportError:
    Github = Auth = None

ROOT = Path(__file__).resolve().parent
NEWS_DIR = ROOT / "news"
RESULTS_DIR = ROOT / "results"
SERIES_FILE = RESULTS_DIR / "attention_series.json"
SERIES_REMOTE_PATH = "data/policy/attention_series.json"

SERIES_DAYS = 120      # 滚动序列最多保留多少天
Z_WINDOW = 30          # z-score 的回看窗口
EMA_WINDOW = 7         # EMA 窗口
MIN_Z_DAYS = 5         # 少于 5 天历史不计算 z
TITLE_WEIGHT = 3       # 标题命中的权重
MIN_EVENT_SHARE = 0.15 # 事件的最低注意力门槛，避免低基数误报
MIN_EVENT_Z = 2.0      # 事件的最低 z 值

# ---------- GitHub ----------
GITHUB_TOKEN = os.environ.get("GH_PAT")
bank_repo = None
if GITHUB_TOKEN and Github and Auth:
    try:
        bank_repo = Github(auth=Auth.Token(GITHUB_TOKEN)).get_repo("wenfp108/Central-Bank")
    except Exception as e:  # token 无效 / 网络问题都不应阻塞本地分析
        print(f"⚠️ 连接 Central-Bank 失败，转为本地模式: {e}")
        bank_repo = None

# ============================================
# 1. 行业词典（支持一个词映射到多个行业）
# ============================================
SECTOR_TERMS = {
    "新能源": [
        "新能源", "新能源汽车", "光伏", "风电", "储能", "新型储能", "氢能", "碳中和",
        "绿色低碳", "清洁能源", "绿电", "充电桩", "动力电池", "锂电", "固态电池",
    ],
    "能源": [
        "能源", "石油", "原油", "天然气", "煤炭", "核电", "电网", "油气", "成品油",
        "电力", "页岩气", "炼化", "特高压", "西电东送",
    ],
    "半导体": [
        "半导体", "芯片", "集成电路", "光刻", "国产替代", "自主可控", "晶圆",
        "封测", "存储芯片", "EDA",
    ],
    "科技": [
        "人工智能", "大模型", "算力", "智算", "数据中心", "数字经济", "机器人",
        "自动驾驶", "量子", "区块链", "6G", "卫星互联网", "低空经济", "商业航天",
        "脑机接口", "元宇宙", "工业互联网",
    ],
    "军工": [
        "军工", "国防", "航天", "卫星", "导弹", "航母", "无人机", "北斗", "战机",
        "军舰", "高超音速", "武器装备", "火箭军",
    ],
    "消费": [
        "消费", "内需", "文旅", "旅游", "餐饮", "零售", "免税", "电商", "以旧换新",
        "服务消费", "夜经济", "冰雪经济", "假日经济", "消费品",
    ],
    "医药": [
        "医药", "医疗", "创新药", "医保", "中药", "生物医药", "医疗器械", "疫苗",
        "集采", "公立医院",
    ],
    "基建": [
        "基建", "高铁", "公路", "水利", "铁路", "桥梁", "城市更新", "新型城镇化",
        "重大工程", "基础设施", "交通强国", "城际铁路", "机场",
    ],
    "金融": [
        "金融", "银行", "证券", "保险", "资本市场", "股市", "货币政策", "信贷",
        "债券", "降准", "降息", "IPO", "融资",
    ],
    "农业": [
        "农业", "粮食", "种业", "乡村振兴", "农机", "化肥", "高标准农田", "大豆",
        "玉米", "小麦", "水稻", "大食物观", "秋粮", "生猪",
    ],
    "房地产": [
        "房地产", "住房", "楼市", "保障房", "公积金", "城中村改造", "存量房",
        "商品房", "土拍", "房企",
    ],
    "汽车": [
        "汽车", "新能源汽车", "智能网联", "车联网", "整车", "零部件", "充电桩",
        "以旧换新",
    ],
}

TERM_SECTORS: dict[str, list[str]] = defaultdict(list)
for _sector, _terms in SECTOR_TERMS.items():
    for _t in _terms:
        if _sector not in TERM_SECTORS[_t]:
            TERM_SECTORS[_t].append(_sector)

# 按长度倒序，保证「新能源汽车」优先于「汽车」
TERM_RE = re.compile("|".join(re.escape(t) for t in sorted(TERM_SECTORS, key=len, reverse=True)))

# 力度/方向词
ACTION_WORDS = {
    "大力推进": 3, "加快推进": 3, "加快发展": 3, "加快": 1, "推进": 1, "推动": 1,
    "支持": 2, "鼓励": 2, "培育": 2, "壮大": 2, "突破": 2, "攻关": 2, "深化": 1,
    "强调": 1, "重要指示": 3, "重要讲话": 3, "规划": 1, "目标": 1, "试点": 1,
    "规范": -1, "整治": -2, "防范": -2, "遏制": -2, "严控": -2, "压减": -2,
    "严禁": -2, "不得": -2, "限制": -2, "打击": -2, "清理": -2, "纠正": -2,
}

# 否定/收紧语境（出现在命中词前后 8 个字内即视为负向）
NEG_WORDS = (
    "防范", "遏制", "严禁", "不得", "禁止", "整治", "压减", "严控",
    "化解", "打击", "清理", "纠正", "限制", "防范化解",
)

# 词语在特定语境下不代表该行业（比喻 / 专有名词）
TERM_EXCLUDE_CONTEXT = {
    "芯片": ("农业", "种子", "种质", "粮食", "饭碗"),
    "卫星": ("卫星城",),
}

NOISE_WORDS = {
    "央视网", "新闻联播", "视频", "nbsp", "消息", "http", "https", "com", "html",
    "VIDE", "查看原文", "习近平", "总书记", "中共中央", "国务院", "中国", "我国",
    "国家", "全国", "今天", "昨天", "上午", "下午", "发展", "建设", "推进", "推动",
    "加强", "加快", "持续", "不断", "全面", "重要", "强调", "指出", "表示", "实现",
    "工作", "会议", "活动", "举行", "召开", "记者", "报道", "有关", "进行", "以及",
    "同时", "目前", "今年", "去年", "已经", "可以", "一个", "我们", "他们", "这个",
}


# ============================================
# 2. 解析新闻文件
# ============================================
def parse_duration(duration_str):
    if not duration_str:
        return 0
    parts = str(duration_str).split(":")
    if len(parts) == 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return 0
    return 0


def parse_news_items(text):
    """把一天的 Markdown 拆成一条条新闻"""
    items = []
    sections = re.split(r"\n### ", text)
    for i, section in enumerate(sections):
        if i == 0:
            continue
        lines = section.strip().split("\n")
        title = lines[0].strip().lstrip("#").strip()
        if not title:
            continue

        duration_str = None
        for line in lines[:6]:
            m = re.search(r"视频时长[：:]*\s*(\d{1,2}):(\d{2})", line.replace("**", ""))
            if m:
                duration_str = f"{m.group(1).zfill(2)}:{m.group(2)}"
                break

        content = "\n".join(lines[1:])
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"\[查看原文\].*", "", content)
        content = re.sub(r"视频时长[：:]*\s*\d{1,2}:\d{2}", "", content)
        content = content.strip()

        items.append(
            {
                "index": i,
                "title": title,
                "content": content,
                "duration_str": duration_str,
                "duration_sec": parse_duration(duration_str),
            }
        )
    return items


# ============================================
# 3. 关键词匹配（最长优先 + 否定语境）
# ============================================
def find_hits(text):
    """返回 [(term, negated), ...]；同一段文本内不重复计数子串"""
    hits = []
    for m in TERM_RE.finditer(text):
        start, end = m.span()
        term = m.group(0)
        ctx = text[max(0, start - 8): min(len(text), end + 8)]
        if any(w in ctx for w in TERM_EXCLUDE_CONTEXT.get(term, ())):
            continue
        negated = any(w in ctx for w in NEG_WORDS)
        hits.append((term, negated))
    return hits


def position_score(index):
    if index <= 3:
        return 10
    if index <= 8:
        return 6
    return 2


def duration_score(sec):
    if sec >= 300:
        return 10
    if sec >= 180:
        return 6
    if sec >= 120:
        return 3
    if sec >= 60:
        return 1
    return 0


def analyze_article(item):
    """单条新闻打分：标题 3 倍权重，负向命中单独统计"""
    title = item.get("title", "")
    body = item.get("content", "")
    full = f"{title} {body}"

    sector_scores = defaultdict(int)
    sector_negative = defaultdict(int)
    matched = []

    title_terms = set()
    for term, negated in find_hits(title):
        matched.append(term)
        if not negated:
            title_terms.add(term)
        for sector in TERM_SECTORS[term]:
            if negated:
                sector_negative[sector] += TITLE_WEIGHT
            else:
                sector_scores[sector] += TITLE_WEIGHT

    for term, negated in find_hits(body):
        matched.append(term)
        for sector in TERM_SECTORS[term]:
            if negated:
                sector_negative[sector] += 1
            else:
                sector_scores[sector] += 1

    signal_score = sum(full.count(w) * v for w, v in ACTION_WORDS.items())
    title_sectors = {s for t in title_terms for s in TERM_SECTORS[t]}
    title_bonus = min(15, 5 * len(title_sectors))

    return {
        "index": item["index"],
        "title": title,
        "duration": item.get("duration_str") or "-",
        "sectors": dict(sorted(sector_scores.items(), key=lambda kv: -kv[1])),
        "negative_sectors": dict(sorted(sector_negative.items(), key=lambda kv: -kv[1])),
        "matched": sorted(set(matched)),
        "mentions": sorted(sector_scores.keys()),
        "signal_score": signal_score,
        "duration_score": duration_score(item.get("duration_sec", 0)),
        "total_score": position_score(item["index"]) + duration_score(item.get("duration_sec", 0)) + signal_score + title_bonus,
    }


# ============================================
# 4. 关键词提取（jieba 可选）
# ============================================
def _clean_keyword(kw):
    kw = (kw or "").strip()
    if len(kw) < 2:
        return False
    if kw in NOISE_WORDS:
        return False
    if re.fullmatch(r"[\d.\s%]+", kw):          # 纯数字 / 百分比
        return False
    if re.fullmatch(r"(19|20)\d{2}", kw):        # 年份
        return False
    return True


def extract_keywords(text, top_n=20):
    if jieba:
        for term in TERM_SECTORS:
            jieba.add_word(term)
        tfidf = [(kw, round(w, 4)) for kw, w in jieba.analyse.extract_tags(text, topK=top_n * 3, withWeight=True)]
        textrank = [(kw, round(w, 4)) for kw, w in jieba.analyse.textrank(text, topK=top_n * 3, withWeight=True)]
        tfidf = [(k, w) for k, w in tfidf if _clean_keyword(k)][:top_n]
        textrank = [(k, w) for k, w in textrank if _clean_keyword(k)][:top_n]
        return {"tfidf": tfidf, "textrank": textrank}

    # 无 jieba 时的降级方案：中文 2-4 字片段词频
    tokens = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    counter = Counter(t for t in tokens if _clean_keyword(t))
    return {"tfidf": counter.most_common(top_n), "textrank": []}


# ============================================
# 5. 滚动统计（z-score / EMA）
# ============================================
def _mean_std(values):
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, var ** 0.5


def rolling_stats(history, attention):
    """history: [{'date','attention','z'}]，返回 ({sector: z}, {sector: ema7})"""
    prev = [h for h in history if h.get("attention")]
    zs, emas = {}, {}
    for sector, value in attention.items():
        series = [h["attention"].get(sector, 0.0) for h in prev[-Z_WINDOW:]]
        if len(series) >= MIN_Z_DAYS:
            mean, std = _mean_std(series)
            if std > 1e-9:
                zs[sector] = round((value - mean) / std, 2)
            elif abs(value - mean) < 1e-9:
                zs[sector] = 0.0
            else:  # 历史完全平稳时，任何变化都按 3σ 处理
                zs[sector] = 3.0 if value > mean else -3.0
        else:
            zs[sector] = None

        recent = [h["attention"].get(sector, 0.0) for h in prev[-EMA_WINDOW:]]
        if recent:
            alpha = 2 / (EMA_WINDOW + 1)
            ema = recent[0]
            for v in recent[1:]:
                ema = alpha * v + (1 - alpha) * ema
            emas[sector] = round(alpha * value + (1 - alpha) * ema, 4)
        else:
            emas[sector] = round(value, 4)
    return zs, emas


def detect_events(zs, history, attention):
    """事件判定：z>=3 直接 strong；z>=2 且近两天也在 1.5 以上才算 sustained/watch。

    单日尖峰 + 低注意力（< MIN_EVENT_SHARE）不报，避免 12 个行业每天随机产出“事件”。
    """
    events = []
    for sector, z in zs.items():
        att = attention.get(sector, 0)
        if z is None or z < MIN_EVENT_Z or att < MIN_EVENT_SHARE:
            continue
        prev_z = [h.get("z", {}).get(sector) for h in history[-2:]]
        sustained = sum(1 for v in prev_z if v is not None and v >= 1.5) >= 1
        if z < 3.0 and not sustained:
            continue
        events.append(
            {
                "sector": sector,
                "z": z,
                "level": "strong" if z >= 3.0 else "watch",
                "sustained": sustained,
                "attention": att,
            }
        )
    return sorted(events, key=lambda e: -e["z"])


# ============================================
# 6. 处理单日
# ============================================
def analyze_text(text, date_str, history=None):
    """纯函数入口，方便测试"""
    items = parse_news_items(text)
    if not items:
        return None

    analyzed = [analyze_article(it) for it in items]
    n = len(analyzed)

    sector_scores = Counter()
    sector_negative = Counter()
    mention_counts = Counter()

    for a in analyzed:
        sector_scores.update(a["sectors"])
        sector_negative.update(a["negative_sectors"])
        for s in a["mentions"]:
            mention_counts[s] += 1

    attention = {s: round(c / n, 4) for s, c in mention_counts.items()}
    attention = dict(sorted(attention.items(), key=lambda kv: -kv[1]))

    history = history or []
    zs, emas = rolling_stats([h for h in history if h.get("date", "") < date_str], attention)
    events = detect_events(zs, [h for h in history if h.get("date", "") < date_str], attention)

    full_text = " ".join(it["title"] + " " + it["content"] for it in items)
    keywords = extract_keywords(full_text)

    return {
        "schema": 2,
        "date": date_str,
        "news_count": n,
        # --- v1 兼容字段 ---
        "sector_scores": dict(sorted(sector_scores.items(), key=lambda kv: -kv[1])),
        "top_keywords": keywords["tfidf"][:10],
        "items": [
            {
                "index": a["index"],
                "title": a["title"],
                "duration": a["duration"],
                "sectors": a["sectors"],
                "signal_score": a["signal_score"],
                "duration_score": a["duration_score"],
                "total_score": a["total_score"],
                "matched": a["matched"][:12],
            }
            for a in analyzed
        ],
        # --- v2 新增字段 ---
        "sector_attention": attention,
        "sector_negative": dict(sorted(sector_negative.items(), key=lambda kv: -kv[1])),
        "sector_z": zs,
        "sector_ema7": emas,
        "events": events,
        "top_keywords_textrank": keywords["textrank"][:10],
    }


def process_day(date_str, history=None):
    year, month = date_str[:4], date_str[4:6]
    md_file = NEWS_DIR / year / month / f"{date_str}.md"
    if not md_file.exists():
        return None
    return analyze_text(md_file.read_text(encoding="utf-8"), date_str, history)


# ============================================
# 7. 滚动序列的读写
# ============================================
def _remote_get(path):
    if not bank_repo:
        return None
    try:
        return json.loads(bank_repo.get_contents(path).decoded_content)
    except Exception:
        return None


def _remote_put(path, payload, message):
    if not bank_repo:
        return False
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        old = bank_repo.get_contents(path)
        bank_repo.update_file(path, message, content, old.sha)
    except Exception:
        bank_repo.create_file(path, message, content)
    return True


def load_series():
    data = _remote_get(SERIES_REMOTE_PATH)
    if data is None and SERIES_FILE.exists():
        try:
            data = json.loads(SERIES_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = None
    return data or {"days": []}


def update_history(history, result):
    entry = {
        "date": result["date"],
        "attention": result["sector_attention"],
        "z": {k: v for k, v in result["sector_z"].items() if v is not None},
    }
    days = [d for d in history if d.get("date") != result["date"]]
    days.append(entry)
    days.sort(key=lambda d: d["date"])
    return days[-SERIES_DAYS:]


def save_series(history):
    payload = {"updated": datetime.now().isoformat(timespec="seconds"), "days": history}
    if bank_repo:
        try:
            if _remote_put(SERIES_REMOTE_PATH, payload, "📈 更新政策注意力序列"):
                print(f"💾 序列已推送: Central-Bank/{SERIES_REMOTE_PATH}")
                return
        except Exception as e:
            print(f"⚠️ 序列推送失败，改为本地保存: {e}")
    RESULTS_DIR.mkdir(exist_ok=True)
    SERIES_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"💾 序列已保存: results/{SERIES_FILE.name}")


# ============================================
# 8. 保存单日结果
# ============================================
def save_result(result):
    if not result:
        return
    date_str = result["date"]
    json_content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    if bank_repo:
        y, m, d = date_str[:4], date_str[4:6], date_str[6:8]
        path = f"data/policy/{y}/{m}/{d}/{date_str}.json"
        try:
            if _remote_put(path, result, f"📰 更新: {date_str} 政策分析"):
                print(f"✅ 已推送: Central-Bank/{path}")
        except Exception as e:
            print(f"❌ 推送失败: {e}")
    else:
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / f"{date_str}.json").write_text(json_content, encoding="utf-8")
        print(f"✅ 已保存: results/{date_str}.json")


# ============================================
# 9. 报告
# ============================================
def generate_report(result, trends=None):
    if not result:
        return ""
    md = f"# 📰 新闻联播政策信号分析 ({result['date']})\n\n"
    md += f"> 新闻 {result['news_count']} 条 · schema v{result.get('schema', 1)}\n\n"

    if result.get("events"):
        md += "## ⚠️ 异常信号\n\n"
        for e in result["events"]:
            tag = "持续" if e.get("sustained") else "单日"
            md += f"- **{e['sector']}** z={e['z']} ({e['level']}, {tag})\n"
        md += "\n"

    md += "## 📊 行业注意力\n\n| 行业 | 注意力 | 7日均线 | z | 负向 |\n|:---|---:|---:|---:|---:|\n"
    for sector, att in result["sector_attention"].items():
        z = result["sector_z"].get(sector)
        md += (
            f"| {sector} | {att * 100:.0f}% | {result['sector_ema7'].get(sector, 0) * 100:.0f}% "
            f"| {z if z is not None else '—'} | {result['sector_negative'].get(sector, 0)} |\n"
        )
    md += "\n"

    md += "## 🔥 重点新闻\n\n| 分数 | 时长 | 标题 | 行业 |\n|:---|---:|:---|:---|\n"
    for item in sorted(result["items"], key=lambda x: -x["total_score"])[:6]:
        sectors = ", ".join(item["sectors"].keys()) or "-"
        md += f"| {item['total_score']} | {item['duration']} | {item['title'][:42]} | {sectors} |\n"
    md += "\n## 🔑 关键词\n\n"
    md += " · ".join(k for k, _ in result["top_keywords"]) + "\n"

    if trends:
        md += f"\n## 📈 近 {trends['days']} 天\n\n"
        for sector, info in list(trends["sector_trend"].items())[:8]:
            md += f"- {sector}: 均值 {info['avg'] * 100:.0f}% · 最新 {info['latest'] * 100:.0f}%\n"
    return md


def analyze_trends(days=7, until=None):
    files = sorted(f for f in NEWS_DIR.rglob("*.md") if re.fullmatch(r"\d{8}", f.stem))
    if until:
        files = [f for f in files if f.stem <= until]
    if not files:
        return None
    recent = files[-days:]
    sector_values = defaultdict(list)
    keyword_freq = Counter()

    for f in recent:
        result = process_day(f.stem)
        if not result:
            continue
        for sector, att in result["sector_attention"].items():
            sector_values[sector].append(att)
        for kw, _ in result["top_keywords"]:
            keyword_freq[kw] += 1

    trend = {}
    for sector, values in sector_values.items():
        trend[sector] = {"avg": sum(values) / len(values), "latest": values[-1], "days": len(values)}

    return {
        "period": f"{recent[0].stem} ~ {recent[-1].stem}",
        "days": len(recent),
        "sector_trend": dict(sorted(trend.items(), key=lambda kv: -kv[1]["latest"])),
        "top_keywords": keyword_freq.most_common(20),
    }


# ============================================
# 10. 批量处理
# ============================================
def process_all():
    files = sorted(NEWS_DIR.rglob("*.md"))
    if not files:
        print("⚠️ 无新闻文件")
        return

    print(f"📊 开始处理 {len(files)} 天的新闻…")
    # 批量重建滚动序列，避免上次运行被截断的序列影响早期 z-score
    history = []
    ok = 0
    for f in files:
        date_str = f.stem
        if not re.fullmatch(r"\d{8}", date_str):
            continue
        result = process_day(date_str, history)
        if not result:
            print(f"⚠️ 跳过: {date_str}")
            continue
        save_result(result)
        history = update_history(history, result)
        ok += 1

    save_series(history)
    print(f"✅ 完成 {ok} 天")


# ============================================
# 11. CLI
# ============================================
def _handle_one(date_str):
    history = load_series()["days"]
    result = process_day(date_str, history)
    if not result:
        print(f"⚠️ 无数据: {date_str}")
        return None
    save_result(result)
    save_series(update_history(history, result))
    return result


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        files = [f for f in sorted(NEWS_DIR.rglob("*.md")) if re.fullmatch(r"\d{8}", f.stem)]
        if not files:
            print("⚠️ 无数据")
        else:
            result = _handle_one(files[-1].stem)
            if result:
                print(generate_report(result))

    elif cmd == "all":
        process_all()

    elif cmd == "date":
        if len(sys.argv) < 3:
            print("用法: python policy_nlp.py date 20261006")
            sys.exit(1)
        result = _handle_one(sys.argv[2])
        if result:
            print(generate_report(result))

    elif cmd == "trends":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        trends = analyze_trends(days)
        if not trends:
            print("⚠️ 无数据")
        else:
            print(f"\n📈 趋势分析 ({trends['period']})，覆盖 {trends['days']} 天\n")
            for sector, info in trends["sector_trend"].items():
                print(f"  {sector:6} 均值 {info['avg'] * 100:5.1f}%  最新 {info['latest'] * 100:5.1f}%")
            print("\n🔑 高频关键词：")
            print("  " + " · ".join(k for k, _ in trends["top_keywords"][:15]))

    elif cmd == "report":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        if not date_str:
            files = [f for f in sorted(NEWS_DIR.rglob("*.md")) if re.fullmatch(r"\d{8}", f.stem)]
            date_str = files[-1].stem
        result = process_day(date_str, load_series()["days"])
        print(generate_report(result, analyze_trends(7, date_str)) if result else "⚠️ 无数据")

    else:
        print("用法：")
        print("  python policy_nlp.py run                  # 分析最新一天")
        print("  python policy_nlp.py date 20261006        # 指定日期")
        print("  python policy_nlp.py all                  # 批量处理")
        print("  python policy_nlp.py trends 7             # 近 7 天趋势")
        print("  python policy_nlp.py report 20261006      # 打印报告")
