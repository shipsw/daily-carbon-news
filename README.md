# 🌿 Daily Carbon News

> 全球碳中和 · 境外媒体新闻每日聚合

从 22 家国际主流媒体，通过 40 组碳中和相关中英文关键词，自动抓取匹配新闻，生成每日更新的信息看板。

## 📰 覆盖媒体

| 地区 | 媒体 |
|------|------|
| 🇺🇸 美国 | NYT, Washington Post, WSJ, LA Times, USA Today, Bloomberg, CNN |
| 🇬🇧 英国 | The Times, Guardian, Daily Telegraph, Independent, Financial Times, Daily Mail, The Sun, BBC, Reuters |
| 🇪🇺 欧洲 | Euronews, Politico Europe, Euractiv |
| 🇫🇷 法国 | AFP |
| 🇪🇸 西班牙 | El País |
| 🇸🇬 新加坡 | Business Times |

## 🔑 关键词（40组）

覆盖：碳中和、碳达峰、气候变化、可再生能源、碳交易、绿色金融、循环经济、CCUS、碳足迹、能源转型等。

## 🚀 快速开始

### 本地预览

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 抓取新闻
python fetch_news.py

# 3. 本地启动 HTTP 服务
python -m http.server 8080

# 4. 浏览器访问
# http://localhost:8080
```

### GitHub Pages 部署（自动更新）

1. 将此仓库推送到 GitHub
2. 仓库 Settings → Pages → 选择 **GitHub Actions**
3. Actions 会自动每天 8:00、14:00、20:00（北京时间）运行
4. 页面自动部署到 `https://<你的用户名>.github.io/daily-carbon-news/`

## ⚙️ 工作原理

```
Google News RSS (免费)  →  Python 爬虫  →  data/news.json  →  静态网页
                                                            ↓
                                              GitHub Actions 每天定时更新
```

- **数据源**: Google News RSS（完全免费，无需 API Key）
- **匹配引擎**: 中英文关键词模糊匹配
- **更新频率**: 每天 3 次（北京时间 8:00 / 14:00 / 20:00）
- **去重机制**: 基于 URL 自动去重，保留最多 500 条

## 📁 项目结构

```
daily-carbon-news/
├── index.html                # 网页前端
├── fetch_news.py             # 爬虫脚本
├── requirements.txt          # Python 依赖
├── config/
│   ├── keywords.json         # 40 组关键词
│   └── media.json            # 22 家媒体
├── data/
│   └── news.json             # 新闻数据缓存
└── .github/workflows/
    └── daily.yml             # GitHub Actions 自动更新
```
