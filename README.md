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

`policy_nlp.py` — jieba 分词 + 关键词提取 + 行业映射 + 权重打分

### 权重计算

| 维度 | 逻辑 | 分值 |
|:---|:---|:---|
| **序号分** | 新闻联播按重要性排序 | 第1条=10分，第2条=9分... |
| **时长分** | 视频时长反映重要程度 | ≥5分钟=10分，≥3分钟=6分，≥2分钟=3分 |
| **信号词** | 政策力度关键词 | "重要指示"=5分，"大力推进"=3分，"强调"=3分 |
| **标题加分** | 标题命中行业关键词 | 每个+5分 |

### 行业映射 (11个板块)

新能源 | 半导体 | 科技 | 军工 | 消费 | 医药 | 基建 | 金融 | 农业 | 房地产 | 能源

### 使用方法

```bash
python policy_nlp.py run        # 分析最新一天（推送到 Central-Bank）
python policy_nlp.py all        # 批量处理所有
python policy_nlp.py trends 7   # 7天趋势
python policy_nlp.py date 20260508  # 指定日期
```

## 关联仓库

| 仓库 | 用途 |
|:---|:---|
| [xin-wen-lian-bo](https://github.com/wenfp108/xin-wen-lian-bo) | 本仓库。爬虫 + NLP 分析 |
| [Central-Bank](https://github.com/wenfp108/Central-Bank) | 数据存储。policy 分析结果 |
| [refinery-erngine](https://github.com/wenfp108/refinery-erngine) | 情报引擎。读取 Central-Bank 数据 |

## 新闻列表

- [20260531](./news/2026/05/20260531.md)
- [20260530](./news/2026/05/20260530.md)
- [20260529](./news/2026/05/20260529.md)
- [20260528](./news/2026/05/20260528.md)
- [20260527](./news/2026/05/20260527.md)
- [20260526](./news/2026/05/20260526.md)
- [20260525](./news/2026/05/20260525.md)
