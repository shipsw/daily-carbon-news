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


def batch_translate(items, key="title", max_workers=5):
    """并发批量翻译"""
    if not _translation_available:
        return items
    
    texts = [(i, item.get(key, "")) for i, item in enumerate(items) if item.get(key)]
    if not texts:
        return items
    
    print(f"  \U0001f310 正在翻译 {len(texts)} 条 {key}...")
    
    def do_translate(idx, txt):
        try:
            has_en = any(c.isascii() and c.isalpha() for c in txt)
            if not has_en or len(txt) < 10:
                return idx, txt
            result = _translator.translate(txt[:2000])
            if result and result != txt:
                return idx, result
        except Exception:
            pass
        return idx, txt
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(do_translate, idx, txt): idx for idx, txt in texts}
        for future in as_completed(futures):
            idx, translated = future.result()
            items[idx][key + "_zh"] = translated
    
    done = sum(1 for item in items if item.get(key + "_zh") and item[key + "_zh"] != item[key])
    print(f"  \u2705 {key} 翻译完成: {done}/{len(texts)}")
    return items


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

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

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
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en&tbs=qdr:w"

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

    # 构建搜索查询
    en_keywords = [kw["en"] for kw in keywords]
    zh_keywords = [kw["zh"] for kw in keywords]

    # 按媒体域名构建 site 查询
    domains = [m["domain"] for m in media_list]
    site_queries = " OR ".join([f"site:{d}" for d in domains])

    # 英文关键词搜索（批量）
    print("🔍 搜索英文关键词...")
    batch_size = 5  # 每批 5 个关键词，避免查询过长
    for i in range(0, len(en_keywords), batch_size):
        batch = en_keywords[i : i + batch_size]
        kw_query = " OR ".join([f'"{kw}"' for kw in batch])
        full_query = f"({kw_query}) ({site_queries})"
        print(f"  批次 {i//batch_size + 1}: {batch[0]}...")

        items = fetch_google_news_rss(full_query, num_results=20)

        # 标记匹配的关键词
        for item in items:
            text_to_check = f"{item['title']} {item['snippet']}"
            item["matched_keywords"] = match_keywords(text_to_check, keywords)

        all_news.extend(items)
        time.sleep(1)  # 礼貌延迟

    # 中文关键词搜索（批量）
    print("\n🔍 搜索中文关键词...")
    for i in range(0, len(zh_keywords), batch_size):
        batch = zh_keywords[i : i + batch_size]
        kw_query = " OR ".join([f'"{kw}"' for kw in batch])
        full_query = f"({kw_query}) ({site_queries})"
        print(f"  批次 {i//batch_size + 1}: {batch[0]}...")

        items = fetch_google_news_rss(full_query, num_results=20)

        for item in items:
            text_to_check = f"{item['title']} {item['snippet']}"
            item["matched_keywords"] = match_keywords(text_to_check, keywords)

        all_news.extend(items)
        time.sleep(1)

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

    # 过滤：只保留最近 2 天的新闻
    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=168)  # 最近 7 天
    before = len(unique_news)
    unique_news = [
        n for n in unique_news
        if n.get("published") and _parse_date(n["published"]) >= cutoff
    ]
    after = len(unique_news)
    print(f"  🕐 过滤掉 {before - after} 条过期新闻，保留最近 7 天共 {after} 条")

    # 按时间倒序
    unique_news.sort(key=lambda x: x.get("published", ""), reverse=True)

    # 精简 Google News 链接
    unique_news = resolve_links(unique_news)
    print(f"  🔗 已精简 {len(unique_news)} 条链接")

    # 批量翻译标题到中文
    unique_news = batch_translate(unique_news, key="title", max_workers=8)

    # 统计翻译情况
    translated_count = sum(1 for n in unique_news if n.get("title_zh") and n["title_zh"] != n["title"])
    print(f"🌐 翻译完成: {translated_count} 条标题已转为中文")

    # 保存
    saved = save_news(unique_news)

    print(f"\n✅ 任务完成！当前共 {len(saved)} 条新闻数据")
    return saved


if __name__ == "__main__":
    run()
