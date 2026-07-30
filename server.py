#!/usr/bin/env python3
"""
Daily Carbon News - HTTP Server with Short URL Redirect Service
短网址服务 + 静态文件服务器
"""

import json
import os
import sys
import io
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

# Windows 终端编码适配
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TZ = timezone(timedelta(hours=8))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
URL_MAP_PATH = os.path.join(DATA_DIR, "url_map.json")
CLICK_LOG_PATH = os.path.join(DATA_DIR, "click_log.json")

DEFAULT_PORT = 8000


def load_url_map():
    """加载短网址映射表"""
    if not os.path.exists(URL_MAP_PATH):
        return {}
    try:
        with open(URL_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_url_map(url_map):
    """保存短网址映射表"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(URL_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)


def log_click(code, url, referer="", user_agent=""):
    """记录点击日志"""
    os.makedirs(DATA_DIR, exist_ok=True)
    logs = []
    if os.path.exists(CLICK_LOG_PATH):
        try:
            with open(CLICK_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, IOError):
            logs = []
    
    logs.append({
        "code": code,
        "url": url,
        "time": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "referer": referer,
        "user_agent": user_agent[:200] if user_agent else "",
    })
    
    # 最多保留 10000 条日志
    if len(logs) > 10000:
        logs = logs[-10000:]
    
    with open(CLICK_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


class ShortURLHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器，支持短网址重定向"""
    
    def do_GET(self):
        self._route_request()
    
    def do_HEAD(self):
        self._route_request(method="HEAD")
    
    def _route_request(self, method="GET"):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # 处理短网址重定向: /s/<code>
        if path.startswith("/s/") and len(path) > 3:
            code = path[3:].strip("/")
            if method == "HEAD":
                self._handle_short_url_head(code)
            else:
                self._handle_short_url(code)
            return
        
        # 处理统计页面: /stats
        if path == "/stats":
            self._handle_stats()
            return
        
        # 处理 API 查询: /api/url-map
        if path == "/api/url-map":
            self._handle_api_url_map()
            return
        
        # 处理 API 点击统计: /api/click-log
        if path == "/api/click-log":
            self._handle_api_click_log()
            return
        
        # 默认: 静态文件服务
        if method == "GET":
            return super().do_GET()
        else:
            # HEAD 请求，发送响应头即可
            return super().do_HEAD()
    
    def _handle_short_url_head(self, code):
        """处理短网址 HEAD 请求（仅返回响应头）"""
        url_map = load_url_map()
        entry = url_map.get(code)
        if entry is None:
            self.send_response(302)
            self.send_header("Location", "/?error=404&code=" + code)
            self.end_headers()
            return
        target_url = entry.get("url", "")
        if not target_url:
            self.send_response(302)
            self.send_header("Location", "/?error=empty")
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", target_url)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
    
    def _handle_short_url(self, code):
        """处理短网址重定向"""
        url_map = load_url_map()
        
        entry = url_map.get(code)
        if entry is None:
            # 404 页面
            self.send_response(302)
            self.send_header("Location", "/?error=404&code=" + code)
            self.end_headers()
            return
        
        target_url = entry.get("url", "")
        if not target_url:
            self.send_response(302)
            self.send_header("Location", "/?error=empty")
            self.end_headers()
            return
        
        # 记录点击
        referer = self.headers.get("Referer", "")
        user_agent = self.headers.get("User-Agent", "")
        log_click(code, target_url, referer, user_agent)
        
        # 更新点击计数
        entry["clicks"] = entry.get("clicks", 0) + 1
        entry["last_click"] = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        save_url_map(url_map)
        
        # 重定向到原始 URL
        self.send_response(302)
        self.send_header("Location", target_url)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
    
    def _handle_stats(self):
        """显示统计页面"""
        url_map = load_url_map()
        
        total_links = len(url_map)
        total_clicks = sum(e.get("clicks", 0) for e in url_map.values())
        
        # 按点击数排序
        sorted_links = sorted(url_map.items(), key=lambda x: x[1].get("clicks", 0), reverse=True)
        top_links = sorted_links[:50]
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Daily Carbon News - 短网址统计</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f0f4f0; color: #1a2a1a; padding: 1.5rem; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 1rem; color: #2d8a4e; }}
        .summary {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
        .card {{ background: white; border-radius: 10px; padding: 1rem 1.5rem;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.06); flex: 1; min-width: 120px; }}
        .card .num {{ font-size: 1.8rem; font-weight: 700; color: #2d8a4e; }}
        .card .label {{ font-size: 0.8rem; color: #5a6a5a; }}
        table {{ width: 100%; background: white; border-radius: 10px; overflow: hidden;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-collapse: collapse; }}
        th {{ background: #2d8a4e; color: white; padding: 0.6rem 0.8rem; font-size: 0.8rem; text-align: left; }}
        td {{ padding: 0.5rem 0.8rem; font-size: 0.82rem; border-bottom: 1px solid #e0e8e0; }}
        tr:hover td {{ background: #f5faf5; }}
        .code {{ font-family: monospace; background: #e8f5e9; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.78rem; }}
        .url-cell {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .url-cell a {{ color: #1a73e8; text-decoration: none; }}
        .url-cell a:hover {{ text-decoration: underline; }}
        .back {{ display: inline-block; margin-bottom: 1rem; color: #2d8a4e; text-decoration: none; font-size: 0.9rem; }}
        .back:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back">← 返回首页</a>
        <h1>📊 短网址统计</h1>
        <div class="summary">
            <div class="card"><div class="num">{total_links}</div><div class="label">总链接数</div></div>
            <div class="card"><div class="num">{total_clicks}</div><div class="label">总点击数</div></div>
        </div>
        <table>
            <thead><tr><th>短码</th><th>短链接</th><th>原始 URL</th><th>点击</th><th>创建时间</th><th>最后点击</th></tr></thead>
            <tbody>
        """
        
        for code, entry in top_links:
            title = entry.get("title", "")[:60]
            target_url = entry.get("url", "")
            clicks = entry.get("clicks", 0)
            created = entry.get("created", "")
            last_click = entry.get("last_click", "-")
            
            html += f"""<tr>
                <td><span class="code">{code}</span></td>
                <td><a href="/s/{code}" target="_blank">/s/{code}</a></td>
                <td class="url-cell"><a href="{target_url}" target="_blank" title="{title}">{target_url[:60]}</a></td>
                <td>{clicks}</td>
                <td>{created}</td>
                <td>{last_click}</td>
            </tr>"""
        
        html += """
            </tbody>
        </table>
        <p style="margin-top:1rem;font-size:0.78rem;color:#5a6a5a;">
            * 显示点击量最高的 50 条链接
        </p>
    </div>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    
    def _handle_api_url_map(self):
        """提供 URL 映射 JSON API"""
        url_map = load_url_map()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(url_map, ensure_ascii=False, indent=2).encode("utf-8"))
    
    def _handle_api_click_log(self):
        """提供点击日志 JSON API"""
        logs = []
        if os.path.exists(CLICK_LOG_PATH):
            try:
                with open(CLICK_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                logs = []
        
        # 返回最近 500 条
        logs = logs[-500:]
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(logs, ensure_ascii=False, indent=2).encode("utf-8"))
    
    def log_message(self, format, *args):
        """自定义日志输出"""
        msg = format % args
        print(f"  📡 {self.address_string()} - {msg}")


def run_server(port=DEFAULT_PORT):
    """启动 HTTP 服务器"""
    server_addr = ("0.0.0.0", port)
    httpd = HTTPServer(server_addr, ShortURLHandler)
    
    print(f"\n{'='*60}")
    print(f"🌿 Daily Carbon News Server")
    print(f"📍 服务器地址: http://localhost:{port}")
    print(f"🔗 短网址服务: http://localhost:{port}/s/<短码>")
    print(f"📊 统计面板:   http://localhost:{port}/stats")
    print(f"{'='*60}\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务器已关闭")
        httpd.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Daily Carbon News Server")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help=f"端口号 (默认: {DEFAULT_PORT})")
    args = parser.parse_args()
    run_server(args.port)
