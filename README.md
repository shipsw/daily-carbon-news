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
- **去重机制**: 基于 URL 自动去重，保留最多 2000 条

## 🌐 翻译机制

新闻标题自动翻译为中文，采用**双翻译源**策略：

1. **Google 翻译**（主）：质量高；被限流时自动切换备选源
2. **MyMemory**（备）：Google 不可用时自动启用

为避免触发限流：
- 只翻译新增新闻（复用已有翻译结果）
- 每次运行额外回填最多 30 条历史未翻译标题
- 请求间加延迟控制，失败自动重试

**可选：提升翻译配额**

MyMemory 匿名配额约 1000 词/天，配置邮箱后提升到 50000 字符/天：

1. 仓库 **Settings → Secrets and variables → Actions**
2. 新建 Secret：`MYMEMORY_EMAIL` = 你的邮箱
3. GitHub Actions 会自动读取该 Secret

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
