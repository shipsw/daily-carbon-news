#!/usr/bin/env python3
"""
Daily Carbon News - Google News RSS Fetcher
利用 Google News RSS 免费获取境外媒体新闻，按关键词匹配筛选。
"""

import json
import time
import os
import hashlib
import sys
import io
import secrets
import string
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from xml.etree import ElementTree as ET

# Windows 终端编码适配
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 翻译模块 - 使用 deep-translator
try:
    from deep_translator import GoogleTranslator
    _translator = GoogleTranslator(source='en', target='zh-CN')
    _translation_available = True
except Exception:
    _translation_available = False


def translate_to_zh(text):
    """翻译单条文本"""
    if not text or not _translation_available:
        return text
    try:
        has_english = any(c.isascii() and c.isalpha() for c in text)
        if not has_english or len(text) < 10:
            return text
        return _translator.translate(text[:2000])
    except Exception:
        pass
    return text


def batch_translate(items, key="title", max_workers=3):
    """串行翻译（避免线程安全问题）"""
    if not _translation_available:
        return items
    
    texts = [(i, item.get(key, "")) for i, item in enumerate(items) if item.get(key)]
    if not texts:
        return items
    
    print(f"  🌐 正在翻译 {len(texts)} 条 {key}...")
    
    done = 0
    for idx, txt in texts:
        try:
            has_en = any(c.isascii() and c.isalpha() for c in txt)
            if has_en and len(txt) >= 10:
                result = _translator.translate(txt[:2000])
                if result and result != txt:
                    items[idx][key + "_zh"] = result
                    done += 1
                    continue
        except Exception:
            pass
        items[idx][key + "_zh"] = txt
    
    print(f"  ✅ {key} 翻译完成: {done}/{len(texts)}")
    return items


def generate_short_code(length=7):
    """生成随机短码 (a-zA-Z0-9)"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def load_url_map():
    """加载现有的短网址映射表"""
    path = os.path.join(DATA_DIR, "url_map.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_url_map(url_map):
    """保存短网址映射表"""
    path = os.path.join(DATA_DIR, "url_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)
    print(f"  🔗 短网址映射已保存 ({len(url_map)} 条)")


def assign_short_links(news_items):
    """为新闻条目分配短码，返回 (items, url_map)"""
    url_map = load_url_map()
    existing_codes = set(url_map.keys())
    
    for item in news_items:
        original_url = item.get("link", "")
        if not original_url:
            continue
        
        # 如果该 URL 已有短码，直接复用
        existing_code = None
        for code, entry in url_map.items():
            if entry.get("url") == original_url:
                existing_code = code
                break
        
        if existing_code:
            item["short_code"] = existing_code
            item["short_link"] = f"/s/{existing_code}"
            continue
        
        # 生成唯一短码
        for _ in range(100):  # 最多尝试 100 次
            code = generate_short_code()
            if code not in existing_codes:
                break
        else:
            # 极端情况：扩容
            code = generate_short_code(8)
        
        existing_codes.add(code)
        item["short_code"] = code
        item["short_link"] = f"/s/{code}"
        
        # 记录映射
        url_map[code] = {
            "url": original_url,
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "created": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "clicks": 0
        }
    
    return news_items, url_map


def clean_google_link(url):
    """精简 Google News 链接，去掉追踪参数"""
    if "news.google.com" not in url:
        return url
    # 去掉 oc=5, hl=, gl=, ceid= 等追踪参数
    import re
    url = re.sub(r"[?&]oc=\d+", "", url)
    url = re.sub(r"[?&]hl=[^&]+", "", url)
    url = re.sub(r"[?&]gl=[^&]+", "", url)
    url = re.sub(r"[?&]ceid=[^&]+", "", url)
    url = url.rstrip("?&")  # 去掉尾部残留符号
    return url


def resolve_links(items, max_workers=15):
    """精简 Google News 跳转链接（去掉追踪参数）"""
    for item in items:
        link = item.get("link", "")
        if link and "news.google.com" in link:
            item["link"] = clean_google_link(link)
    return items


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_FILE = os.path.join(DATA_DIR, "news.json")

# 时区（北京时间）
TZ = timezone(timedelta(hours=8))


def load_config(filename):
    with open(os.path.join(CONFIG_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


def save_news(news_items):
    """保存新闻数据，增量合并（保留历史数据）"""
    existing = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    # 用链接去重
    seen_urls = {item["link"] for item in existing}
    for item in news_items:
        if item["link"] not in seen_urls:
            existing.append(item)
            seen_urls.add(item["link"])

    # 按时间倒序排列
    existing.sort(key=lambda x: x.get("published", ""), reverse=True)

    # 最多保留 2000 条
    if len(existing) > 2000:
        existing = existing[:2000]

    # 生成短链接
    existing, url_map = assign_short_links(existing)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # 保存 URL 映射
    save_url_map(url_map)

    print(f"✅ 已保存 {len(existing)} 条新闻到 {OUTPUT_FILE}")
    return existing


def fetch_google_news_rss(query, num_results=20):
    """
    通过 Google News RSS 搜索新闻
    Google News RSS 完全免费，无 API Key 要求
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    encoded_query = quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en&num=100"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ Google News RSS 请求失败: {e}")
        return []

    items = []
    try:
        root = ET.fromstring(resp.content)
        ns = {"": "http://www.w3.org/2005/Atom"}

        # RSS 2.0 format
        for entry in root.findall(".//item"):
            title = entry.findtext("title", "").strip()
            link = entry.findtext("link", "").strip()
            pub_date_str = entry.findtext("pubDate", "").strip()
            source = entry.findtext("source", "").strip()
            description = entry.findtext("description", "").strip()

            # 清理 HTML 标签
            description = description.replace("<![CDATA[", "").replace("]]>", "")
            # 简单去除 HTML 标签
            import re
            description = re.sub(r"<[^>]+>", "", description)

            # 解析时间
            published = ""
            if pub_date_str:
                try:
                    # RSS 时间格式: Mon, 01 Jan 2024 12:00:00 GMT
                    clean = pub_date_str.replace("GMT", "+0000").replace("UTC", "+0000").strip()
                    dt = datetime.strptime(clean, "%a, %d %b %Y %H:%M:%S %z")
                    published = dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, IndexError):
                    published = pub_date_str

            # 从 description 中提取摘要（Google News 的描述里常包含源信息）
            snippet = description if description else ""

            items.append({
                "title": title,
                "link": link,
                "source": source,
                "published": published,
                "snippet": snippet,
                "matched_keywords": [],
            })

    except ET.ParseError as e:
        print(f"⚠️ RSS 解析失败: {e}")
        return []

    return items


def match_keywords(item_text, keywords):
    """检查文本是否匹配任何关键词（中文/英文）"""
    matched = []
    item_lower = item_text.lower()
    for kw in keywords:
        zh = kw["zh"].lower()
        en = kw["en"].lower()
        if zh and zh in item_lower:
            matched.append(kw["zh"])
        elif en and en in item_lower:
            matched.append(kw["en"])
    return matched


def _parse_date(date_str):
    """解析日期字符串为 datetime 对象"""
    if not date_str:
        return datetime.min.replace(tzinfo=TZ)
    # 已经是 YYYY-MM-DD HH:MM:SS 格式
    if len(date_str) >= 10 and date_str[4] == "-":
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=TZ)


def run():
    """主流程"""
    print(f"\n{'='*60}")
    print(f"🌿 Daily Carbon News 抓取任务")
    print(f"🕐 运行时间: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    config_keywords = load_config("keywords.json")
    config_media = load_config("media.json")

    keywords = config_keywords["keywords"]
    media_list = config_media["media"]

    all_news = []

    # 策略：对每个媒体 + 每组关键词组合搜索
    # 但为了避免请求过多，采用分组策略：
    # 1. 用英文关键词搜全部媒体（一次搜索多个关键词）
    # 2. 再用中文关键词搜

    # 构建搜索查询 - 广泛搜索 + 来源过滤
    en_keywords = [kw["en"] for kw in keywords]
    zh_keywords = [kw["zh"] for kw in keywords]
    domains = [m["domain"] for m in media_list]
    media_names = [m["name"] for m in media_list]

    def is_valid_source(source):
        """检查来源是否在我们关注的媒体列表中"""
        if not source:
            return False
        s = source.lower()
        # 域名匹配
        for d in domains:
            d_clean = d.replace("www.", "")
            if d_clean in s:
                return True
        # 名称匹配
        for mn in media_names:
            if mn.lower() in s:
                return True
        # 额外常用名称 - 扩大气候/能源类相关媒体
        extra = ["reuters", "bbc", "bloomberg", "wsj", "cnn", "euractiv", 
                 "politico", "carbon brief", "inside climate", "e&e news",
                 "climate home", "the hill", "ap news", "associated press",
                 "npr", "propublica", "the conversation", "axios",
                 "business green", "edie", "pv magazine", "recharge",
                 "energy monitor", "ieefa", "the energy collective",
                 "sustainable brands", "environmental leader",
                 "greentech media", "canary media", "grist",
                 "newsweek", "time", "economist", "forbes",
                 "new scientist", "national geographic",
                 "scientific american", "science daily"]
        for e in extra:
            if e in s:
                return True
        return False

    # 策略1: 按关键词主题分组搜索
    topic_groups = [
        "climate change global warming emissions",
        "carbon neutrality net zero emissions",
        "renewable energy solar wind clean power",
        "energy transition fossil fuel green",
        "electric vehicle EV carbon tax trading",
        "green finance sustainable investment ESG",
        "circular economy climate policy decarbonization",
        "carbon footprint carbon capture hydrogen energy",
        "carbon trading emission offset credits",
        "energy efficiency smart grid storage battery",
        "climate resilience adaptation infrastructure",
        "carbon accounting footprint reporting",
    ]

    # 追加媒体专属搜索
    media_searches = [
        "site:nytimes.com climate OR energy OR carbon",
        "site:theguardian.com climate OR energy OR carbon",
        "site:bbc.com climate OR energy OR carbon",
        "site:reuters.com climate OR energy OR carbon",
        "site:bloomberg.com climate OR energy OR carbon",
        "site:washingtonpost.com climate OR energy OR carbon",
        "site:wsj.com climate OR energy OR carbon",
        "site:ft.com climate OR energy OR carbon",
        "site:cnn.com climate OR energy",
        "site:independent.co.uk climate OR energy OR carbon",
        "site:telegraph.co.uk climate OR energy",
        "site:politico.eu climate OR energy",
    ]
    topic_groups.extend(media_searches)

    # 追加单个重要关键词搜索（不带site限制，广泛抓取）
    single_terms = ["climate", "carbon", "renewable", "emissions", "clean energy",
                    "green", "solar", "wind", "electric vehicle", "net zero"]
    topic_groups.extend(single_terms)

    print("🔍 搜索英文主题...")
    for i, topic in enumerate(topic_groups):
        print(f"  主题 {i+1}: {topic[:40]}...")
        items = fetch_google_news_rss(topic, num_results=100)
        for item in items:
            if is_valid_source(item.get("source", "")):
                text = f"{item['title']} {item['snippet']}"
                item["matched_keywords"] = match_keywords(text, keywords)
                if item["matched_keywords"]:
                    all_news.append(item)
        print(f"    -> 获取 {len(items)} 条，当前累计 {len(all_news)} 条")
        time.sleep(0.5)

    # 策略2: 中文关键词搜索
    print("\n🔍 搜索中文关键词...")
    for i in range(0, len(zh_keywords), 10):
        batch = zh_keywords[i : i + 10]
        kw_query = " OR ".join(batch)
        print(f"  批次 {i//10 + 1}: {batch[0]}...")
        items = fetch_google_news_rss(kw_query, num_results=100)
        for item in items:
            if is_valid_source(item.get("source", "")):
                text = f"{item['title']} {item['snippet']}"
                item["matched_keywords"] = match_keywords(text, keywords)
                if item["matched_keywords"]:
                    all_news.append(item)
        print(f"    -> 获取 {len(items)} 条，当前累计 {len(all_news)} 条")
        time.sleep(0.5)

    # 去重
    seen = set()
    unique_news = []
    for item in all_news:
        # 用标题 + 链接去重
        key = f"{item['title']}|{item['link']}"
        if key not in seen:
            seen.add(key)
            unique_news.append(item)

    # 只保留有匹配关键词的结果
    unique_news = [n for n in unique_news if n["matched_keywords"]]

    print(f"\n📊 共获取 {len(unique_news)} 条匹配新闻")

    # 按时间倒序
    unique_news.sort(key=lambda x: x.get("published", ""), reverse=True)

    # 精简 Google News 链接
    unique_news = resolve_links(unique_news)
    print(f"  🔗 精简链接完成")

    # 批量翻译标题到中文
    unique_news = batch_translate(unique_news, key="title")

    # 统计翻译情况
    translated_count = sum(1 for n in unique_news if n.get("title_zh") and n["title_zh"] != n["title"])
    print(f"🌐 翻译完成: {translated_count} 条标题已转为中文")

    # 保存
    saved = save_news(unique_news)

    print(f"\n✅ 任务完成！当前共 {len(saved)} 条新闻数据")
    return saved


if __name__ == "__main__":
    run()
