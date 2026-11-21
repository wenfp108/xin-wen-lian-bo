# 📺 新闻联播文字稿 + NLP 政策分析

> 自动抓取新闻联播文字稿，NLP 分析政策信号，结果推送到 Central-Bank。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│                                                              │
│   ┌──────────────┐              ┌──────────────┐            │
│   │  每日 20:30   │              │  每日 10:00   │            │
│   │  爬虫抓取     │              │  NLP 分析     │            │
│   └──────┬───────┘              └──────┬───────┘            │
│          │                              │                    │
└──────────┼──────────────────────────────┼────────────────────┘
           │                              │
           ▼                              ▼
   ┌───────────────┐              ┌───────────────┐
   │   CCTV 官网    │              │   Central-Bank │
   │  tv.cctv.com   │              │   data/policy/ │
   └───────┬───────┘              └───────────────┘
           │
           ▼
   ┌───────────────┐
   │  news/年/月/   │
   │  YYYYMMDD.md   │
   └───────────────┘
```

## 数据流

```
CCTV 官网 → fetch.js → news/2026/05/20260508.md
                              ↓
                       policy_nlp.py
                              ↓
                    Central-Bank/data/policy/20260508.json
```

## 文件结构

```
xin-wen-lian-bo/
├── index.js              # 爬虫主程序（Node.js）
├── fetch.js              # HTTP 请求封装
├── clean.js              # 历史数据清理
├── policy_nlp.py         # NLP 分析引擎（Python）
├── requirements.txt      # Python 依赖
├── news/
│   └── 2026/
│       ├── 04/
│       │   ├── 20260401.md
│       │   └── ...
│       └── 05/
│           ├── 20260501.md
│           └── ...
└── .github/workflows/
    ├── update.yml        # 每日爬虫
    ├── nlp.yml           # 每日 NLP 分析
    └── clean-data.yml    # 手动清理
```

## NLP 分析

`policy_nlp.py` v2 — 最长匹配 + 否定语境 + 覆盖率注意力 + 30 日滚动异常度。

> 方法、字段和验证结果见 **[docs/nlp.md](docs/nlp.md)**。

### 权重计算

| 维度 | 逻辑 | 分值 |
|:---|:---|:---|
| **序号分** | 新闻联播按重要性排序 | 前 3 条=10 分，4–8 条=6 分，其余=2 分 |
| **时长分** | 视频时长反映重要程度 | ≥5 分钟=10，≥3 分钟=6，≥2 分钟=3 |
| **信号词** | 政策力度关键词 | "重要指示"=+3，"大力推进"=+3，"整治"=-2 |
| **标题加分** | 标题命中行业关键词 | 每个行业 +5（上限 15） |

### 关键指标

| 指标 | 含义 |
|:---|:---|
| `sector_attention` | 提及该行业的新闻条数 / 当日总条数（0–1） |
| `sector_scores` | 加权命中分（v1 兼容字段） |
| `sector_negative` | 负向语境命中（防范 / 整治 / 严控…） |
| `sector_z` | 相对过去 30 天的 z-score |
| `sector_ema7` | 7 日 EMA |
| `events` | z≥2 且注意力≥15% 的异常事件（z≥3 为 strong） |

### 行业映射 (12 个板块)

新能源 | 半导体 | 科技 | 军工 | 消费 | 医药 | 基建 | 金融 | 农业 | 房地产 | 能源 | 汽车

### 使用方法

```bash
python policy_nlp.py run                 # 分析最新一天（推送到 Central-Bank）
python policy_nlp.py all                 # 批量处理所有
python policy_nlp.py trends 7            # 7 天趋势
python policy_nlp.py date 20260508       # 指定日期
python policy_nlp.py report 20260508     # 打印 Markdown 报告
python -m unittest discover -s tests -v  # 单元测试
```

## 关联仓库

| 仓库 | 用途 |
|:---|:---|
| [xin-wen-lian-bo](https://github.com/wenfp108/xin-wen-lian-bo) | 本仓库。爬虫 + NLP 分析 |
| Central-Bank（私有仓库） | 数据存储。policy 分析结果 |
| [refinery-engine](https://github.com/wenfp108/refinery-engine) | 情报引擎。读取 Central-Bank 数据 |

## 新闻列表

- [20261121](./news/2026/11/20261121.md)
- [20261120](./news/2026/11/20261120.md)
- [20261119](./news/2026/11/20261119.md)
- [20261118](./news/2026/11/20261118.md)
- [20261117](./news/2026/11/20261117.md)
- [20261116](./news/2026/11/20261116.md)
- [20261115](./news/2026/11/20261115.md)
