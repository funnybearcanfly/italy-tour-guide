#!/usr/bin/env python3
"""Macro Reports Viewer — Simple Flask webapp with login."""

import os, re, hashlib, secrets, json, html
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string, request, redirect, session, url_for
import markdown2

from trading import bp as trading_bp

BASE_DIR = "/root/projects/macro_reports"
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Single user credentials
USERNAME = "bear"
PASSWORD_HASH = hashlib.sha256("bear2026".encode()).hexdigest()

app = Flask(__name__)
_SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")


def _load_secret_key() -> str:
    """Persist the Flask session signing key so logins survive app restarts."""
    try:
        with open(_SECRET_KEY_FILE) as f:
            k = f.read().strip()
            if k:
                return k
    except FileNotFoundError:
        pass
    k = secrets.token_hex(32)
    with open(_SECRET_KEY_FILE, "w") as f:
        f.write(k)
    try:
        os.chmod(_SECRET_KEY_FILE, 0o600)
    except OSError:
        pass
    return k


app.secret_key = _load_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.register_blueprint(trading_bp)


def md_to_html(text: str) -> str:
    """Convert markdown to clean HTML, with table support."""
    extras = ["tables", "fenced-code-blocks", "header-ids"]
    return markdown2.markdown(text, extras=extras)


def list_reports(category: str) -> list:
    """List reports in a category, newest first."""
    cat_dir = os.path.join(REPORTS_DIR, category)
    if not os.path.isdir(cat_dir):
        return []
    files = []
    for f in os.listdir(cat_dir):
        if f.endswith(".md"):
            path = os.path.join(cat_dir, f)
            stat = os.stat(path)
            title = _format_title(f, category)
            files.append({
                "filename": f,
                "title": title,
                "date": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size": stat.st_size,
            })
    # Weekly: only show reports from 2026-06 onwards
    if category == "weekly":
        files = [x for x in files
                 if x["filename"] >= "2026-06" and not _is_monthly(x["filename"])]
    files.sort(key=lambda x: x["filename"], reverse=True)
    return files


def _format_title(filename: str, category: str) -> str:
    """Format report title for display."""
    name = filename.replace(".md", "")
    if category == "weekly":
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            # Find Sunday of that week (Mon=0, Sun=6)
            days_to_sunday = (6 - dt.weekday()) % 7
            sunday = dt + timedelta(days=days_to_sunday)
            return sunday.strftime("%Y%m%d") + " weekly report"
    return name


def _is_monthly(filename: str) -> bool:
    """Check if filename represents a monthly/biweekly summary."""
    return bool(re.search(r"monthly|biweekly|v\d", filename.lower()))


def read_report(category: str, filename: str) -> str | None:
    """Read a report file."""
    path = os.path.join(REPORTS_DIR, category, filename)
    if not os.path.isfile(path) or ".." in filename:
        return None
    with open(path) as f:
        return f.read()


# ── SEC filings (sec-filing-monitor skill) ──

SEC_DATA_DIR = os.environ.get("SEC_MONITOR_DATA_DIR", os.path.expanduser("~/.sec-filing-monitor"))
SEC_FILINGS_PATH = os.path.join(SEC_DATA_DIR, "filings.json")
LLM_SUMMARIES_PATH = os.path.join(SEC_DATA_DIR, "llm_summaries.jsonl")
NEWS_PATH = os.path.join(SEC_DATA_DIR, "news.json")
NEWS_LLM_SUMMARIES_PATH = os.path.join(SEC_DATA_DIR, "news_llm_summaries.jsonl")


def load_sec_filings() -> list:
    """Load the persisted SEC filings index (newest first)."""
    try:
        with open(SEC_FILINGS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_llm_summaries() -> dict:
    """Load LLM-written human summaries from the JSONL: {accession: summary}."""
    out = {}
    try:
        with open(LLM_SUMMARIES_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    acc = obj.get("accession")
                    s = (obj.get("summary") or "").strip()
                    if acc and s:
                        out[acc] = s
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return out


def load_news() -> list:
    """Load the persisted company-news index (newest first)."""
    try:
        with open(NEWS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_news_llm_summaries() -> dict:
    """Load LLM-written news summaries keyed by url: {url: summary}."""
    out = {}
    try:
        with open(NEWS_LLM_SUMMARIES_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    u = obj.get("url")
                    s = (obj.get("summary") or "").strip()
                    if u and s:
                        out[u] = s
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return out


def filing_documents(filing: dict) -> list:
    """Read the local extracted text for each document of a filing."""
    docs = []
    for d in filing.get("documents", []):
        text = ""
        tp = d.get("text_path")
        if tp and os.path.isfile(tp):
            try:
                with open(tp) as fh:
                    text = fh.read()
            except Exception:
                text = ""
        docs.append({"role": d.get("role", ""), "filename": d.get("filename", ""), "text": text})
    return docs


def form_class(form: str) -> str:
    """CSS class for a form badge, keyed by filing category."""
    base = re.sub(r"/.*$", "", (form or "").upper())
    if base in ("3", "4", "5"):
        return "insider"
    if base in ("10-Q", "10-K", "6-K", "20-F", "40-F", "11-K", "8-K"):
        return "periodic"
    if base.startswith(("S-", "F-")) or base.startswith("424B"):
        return "offering"
    return ""


def is_insider_form(form: str) -> bool:
    """True for insider ownership forms (3/4/5) — low signal, grouped separately."""
    return re.sub(r"/.*$", "", (form or "").upper()) in ("3", "4", "5")


# ── HTML templates (inline for simplicity) ──

LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Reports · Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e1e4e8;font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.login{background:#161b22;padding:48px 40px;border-radius:6px;border:1px solid #30363d;width:360px}
.login h1{font-size:20px;margin-bottom:24px;text-align:center;color:#f0f6fc}
.login input{width:100%;padding:10px 12px;margin-bottom:16px;background:#0d1117;border:1px solid #30363d;
  border-radius:6px;color:#e1e4e8;font-size:14px}
.login input:focus{outline:none;border-color:#8b949e}
.login button{width:100%;padding:10px;background:#238636;border:none;border-radius:6px;color:#fff;
  font-size:14px;cursor:pointer}
.login button:hover{background:#2ea043}
.remember{display:flex;align-items:center;gap:8px;margin:2px 0 16px;color:#8b949e;font-size:13px;
  cursor:pointer;user-select:none}
.remember input{width:auto;margin:0;accent-color:#238636}
.error{color:#f85149;margin-bottom:16px;font-size:13px}
</style>
</head>
<body>
<div class="login">
<h1>Macro Reports</h1>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="post">
<input type="text" name="username" placeholder="用户名" autofocus>
<input type="password" name="password" placeholder="密码">
<label class="remember"><input type="checkbox" name="remember" value="1"> 记住我（30 天内免登录）</label>
<button type="submit">登 录</button>
</form>
</div>
</body>
</html>"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Reports</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e1e4e8;font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;
  max-width:1280px;margin:0 auto;padding:24px 20px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;
  padding-bottom:16px;border-bottom:1px solid #30363d}
.header h1{font-size:18px;color:#f0f6fc}
.header a{color:#8b949e;text-decoration:none;font-size:13px}
.header a:hover{color:#e1e4e8}
.cats{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px}
.cats a{padding:6px 16px;border-radius:6px;text-decoration:none;font-size:13px;
  background:#161b22;color:#8b949e;border:1px solid #30363d}
.cats a.active,.cats a:hover{background:#238636;color:#fff;border-color:#238636}
.report{display:flex;justify-content:space-between;align-items:center;padding:12px 0;
  border-bottom:1px solid #21262d}
.report:hover{background:#161b22;margin:0 -12px;padding:12px;border-radius:6px}
.report .title{font-size:14px;color:#f0f6fc;text-decoration:none}
.report .title:hover{color:#58a6ff}
.report .meta{font-size:12px;color:#8b949e;white-space:nowrap;margin-left:16px}
.empty{text-align:center;color:#8b949e;padding:48px 0;font-size:14px}
</style>
</head>
<body>
<div class="header">
  <h1>📊 Macro Reports</h1>
  <a href="/logout">退出</a>
</div>
<div class="cats">
  <a href="/?cat=daily" class="{{ 'active' if cat=='daily' else '' }}">📰 早报</a>
  <a href="/?cat=weekly" class="{{ 'active' if cat=='weekly' else '' }}">📋 周报</a>
  <a href="/?cat=ishares" class="{{ 'active' if cat=='ishares' else '' }}">📈 iShares ETF</a>
  <a href="/?cat=crypto" class="{{ 'active' if cat=='crypto' else '' }}">🪙 Crypto</a>
  <a href="/?cat=ai_daily_recap" class="{{ 'active' if cat=='ai_daily_recap' else '' }}">AI Daily Recap</a>
  <a href="/?cat=macro_events" class="{{ 'active' if cat=='macro_events' else '' }}">📅 事件监控</a>
  <a href="/sec">📰 公司动态</a>
  <a href="/trading">📊 交易追踪</a>
  <a href="/system">🖥️ 系统监控</a>
</div>
<div class="list">
{% if reports %}
{% for r in reports %}
<div class="report">
  <a class="title" href="/view/{{ cat }}/{{ r.filename }}">{{ r.title }}</a>
  <span class="meta">{{ r.date }}</span>
</div>
{% endfor %}
{% else %}
<div class="empty">暂无报告</div>
{% endif %}
</div>
</body>
</html>"""

REPORT_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e1e4e8;font:14px/1.7 -apple-system,BlinkMacSystemFont,sans-serif;
  max-width:1280px;margin:0 auto;padding:24px 20px}
.back{margin-bottom:16px}
.back a{color:#8b949e;text-decoration:none;font-size:13px}
.back a:hover{color:#58a6ff}
h1,h2,h3,h4{color:#f0f6fc;margin:24px 0 12px}
h1{font-size:22px;border-bottom:1px solid #30363d;padding-bottom:12px}
h2{font-size:18px}
h3{font-size:15px;color:#e1e4e8}
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:12px 0;border-radius:6px}
table{border-collapse:collapse;width:100%;margin:0;font-size:13px;min-width:720px}
th,td{border:1px solid #30363d;padding:8px 12px;text-align:left;vertical-align:top}
th{background:#161b22;color:#f0f6fc;font-weight:600;position:sticky;top:0}
tr:hover{background:#161b22}
a{color:#58a6ff}
code{background:#161b22;padding:2px 6px;border-radius:3px;font-size:13px}
ul,ol{padding-left:24px;margin:8px 0}
li{margin:4px 0}
hr{border:none;border-top:1px solid #30363d;margin:24px 0}
blockquote{border-left:3px solid #30363d;padding:4px 16px;margin:12px 0;color:#8b949e}
strong{color:#f0f6fc}
img{max-width:100%}
@media (max-width:900px){body{padding:20px 14px}table{min-width:640px}}
@media (max-width:640px){body{padding:16px 10px;font-size:13px}h1{font-size:19px}th,td{padding:6px 8px;font-size:12.5px}}
</style>
</head>
<body>
<div class="back"><a href="/?cat={{ cat }}">← 返回列表</a></div>
{{ content|safe }}
</body>
</html>"""

SEC_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SEC Filings</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e6edf3;font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;max-width:1280px;margin:0 auto;padding:28px 22px}
a{color:#58a6ff;text-decoration:none}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #30363d}
.header h1{font-size:19px;color:#f0f6fc;font-weight:600}
.header a{color:#8b949e;font-size:13px}
.header a:hover{color:#e6edf3}
.sub{color:#8b949e;font-size:13px;margin-bottom:22px}
.tabs{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.tabs a{padding:7px 16px;border-radius:8px;background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:13.5px;font-weight:600}
.tabs a:hover{color:#e6edf3;border-color:#8b949e}
.tabs a.active{background:#238636;color:#fff;border-color:#238636}
.filter{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding:10px 12px;background:#161b22;border:1px solid #21262d;border-radius:8px}
.filter .flabel{color:#8b949e;font-size:12.5px;font-weight:600}
.filter .fbtn{padding:4px 12px;border-radius:6px;background:#0f1117;border:1px solid #30363d;color:#8b949e;font-size:12.5px;font-weight:600}
.filter .fbtn:hover{color:#e6edf3;border-color:#8b949e}
.filter .fbtn.on{background:#238636;color:#fff;border-color:#238636}
.filter .fsel{padding:5px 8px;border-radius:6px;background:#0f1117;border:1px solid #30363d;color:#e6edf3;font-size:13px}
.pager{display:flex;align-items:center;gap:8px;margin:24px 0 8px;flex-wrap:wrap}
.pager .pg{padding:6px 12px;border-radius:6px;background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:13px;text-decoration:none}
.pager .pg:hover{color:#e6edf3;border-color:#8b949e}
.pager .pg.cur{background:#238636;color:#fff;border-color:#238636;font-weight:600}
.pager .info{color:#8b949e;font-size:12.5px;margin-left:auto}
.filing{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:18px 20px;margin-bottom:14px}
.filing:hover{border-color:#30363d}
.f-title{color:#f0f6fc;font-size:16.5px;font-weight:600;line-height:1.5;margin-bottom:7px;display:block}
.f-title:hover{color:#58a6ff}
.f-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:7px;font-size:13px;color:#8b949e}
.f-meta .tick{font-size:13.5px}
.f-meta .company{font-size:13px;color:#8b949e;font-weight:500}
.f-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.tick{color:#58a6ff;font-weight:700;font-size:17px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.company{color:#f0f6fc;font-size:14px;font-weight:600}
.form{display:inline-block;background:#238636;color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:10px;letter-spacing:.3px}
.form.insider{background:#6e40c9}
.form.offering{background:#d29922;color:#1b1f24}
.form.periodic{background:#1f6feb}
.f-when{color:#8b949e;font-size:12.5px;margin-bottom:8px}
.f-summary{color:#e6edf3;font-size:14.5px;font-weight:600;line-height:1.55;margin-bottom:2px}
.f-excerpt{color:#9da7b3;font-size:12.5px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.6;white-space:pre-wrap;word-break:break-word;max-height:100px;overflow:hidden;border-left:3px solid #30363d;padding-left:12px;margin:8px 0}
.f-links{font-size:13px;margin-top:2px}
.f-links a{margin-right:18px}
.f-links a:hover{text-decoration:underline}
.empty{text-align:center;color:#8b949e;padding:60px 0}
@media (max-width:640px){body{padding:18px 12px}.filing{padding:14px 14px}.f-title{font-size:15px}}
</style>
</head>
<body>
<div class="header">
  <h1>📰 公司动态</h1>
  <a href="/">← 返回</a>
</div>
<div class="tabs">
  <a href="/sec" class="{{ 'active' if stype=='news' else '' }}">📰 新闻 ({{ n_news }})</a>
  <a href="/sec?type=material" class="{{ 'active' if stype=='material' else '' }}">📄 重要文件 ({{ n_material }})</a>
  <a href="/sec?type=insider" class="{{ 'active' if stype=='insider' else '' }}">👤 内部人交易 ({{ n_insider }})</a>
</div>
{% if stype == 'news' %}
<div class="filter">
  <span class="flabel">时间</span>
  <a class="fbtn {{ 'on' if range_param=='24h' else '' }}" href="/sec?range=24h{% if ticker_param %}&ticker={{ ticker_param }}{% endif %}">24小时</a>
  <a class="fbtn {{ 'on' if range_param=='7d' else '' }}" href="/sec?range=7d{% if ticker_param %}&ticker={{ ticker_param }}{% endif %}">7天</a>
  <a class="fbtn {{ 'on' if range_param=='30d' else '' }}" href="/sec?range=30d{% if ticker_param %}&ticker={{ ticker_param }}{% endif %}">30天</a>
  <a class="fbtn {{ 'on' if range_param=='all' else '' }}" href="/sec?range=all{% if ticker_param %}&ticker={{ ticker_param }}{% endif %}">全部</a>
  <span class="flabel" style="margin-left:10px">公司</span>
  <select class="fsel" onchange="location.href='/sec?range={{ range_param }}&ticker='+encodeURIComponent(this.value)">
    <option value="">全部</option>
    {% for t in all_tickers %}<option value="{{ t }}" {{ 'selected' if ticker_param==t else '' }}>{{ t }}</option>{% endfor %}
  </select>
  {% if ticker_param %}<a class="fbtn" href="/sec?range={{ range_param }}">✕ 清除</a>{% endif %}
</div>
{% endif %}
<div class="sub">数据源：公司新闻室 / RSS + <a href="https://www.sec.gov/edgar" target="_blank" rel="noopener">SEC EDGAR</a> · 「🔗 原文」跳转官方来源</div>
{% if items %}
{% for f in items %}
<div class="filing">
  {% if stype == 'news' %}
  <div class="f-head">
    <span class="tick">${{ f.ticker }}</span>
    <span class="company">{{ f.company or f.ticker }}</span>
    {% if f.display_date %}<span class="f-when" style="margin-left:auto;margin-bottom:0">📅 {% if f.is_capture_date %}收录 {{ f.display_date }}{% else %}{{ f.display_date }}{% endif %}</span>{% endif %}
  </div>
  <a class="f-title" href="{{ f.url }}" target="_blank" rel="noopener">{{ f.title }}</a>
  {% if f.llm_summary or f.clean_summary %}<div class="f-summary">{{ f.llm_summary or f.clean_summary }}</div>{% endif %}
  <div class="f-links"><a href="{{ f.url }}" target="_blank" rel="noopener">🔗 原文 ↗</a></div>
  {% else %}
  <div class="f-head">
    <span class="tick">${{ f.ticker }}</span>
    <span class="company">{{ f.company or f.ticker }}</span>
    <span class="form {{ form_class(f.form) }}">{{ f.form }}</span>
  </div>
  <div class="f-when">📅 {{ f.display_when }}{% if f.sector %} · {{ f.sector }}{% endif %}</div>
  {% if f.display_summary %}<div class="f-summary">{{ f.display_summary }}</div>{% endif %}
  <div class="f-links">
    <a href="/sec/{{ f.accession }}">📖 全文</a>
    <a href="{{ f.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a>
  </div>
  {% endif %}
</div>
{% endfor %}
{% else %}
<div class="empty">暂无内容</div>
{% endif %}
{% if total_pages > 1 %}
<div class="pager">
  {% set q = 'type=' ~ stype ~ '&range=' ~ range_param ~ '&ticker=' ~ ticker_param %}
  {% if page > 1 %}<a class="pg" href="/sec?{{ q }}&page={{ page - 1 }}">‹ 上一页</a>{% endif %}
  {% for p in range(1, total_pages + 1) %}
    {% if p == page %}<span class="pg cur">{{ p }}</span>{% else %}<a class="pg" href="/sec?{{ q }}&page={{ p }}">{{ p }}</a>{% endif %}
  {% endfor %}
  {% if page < total_pages %}<a class="pg" href="/sec?{{ q }}&page={{ page + 1 }}">下一页 ›</a>{% endif %}
  <span class="info">第 {{ page }} / {{ total_pages }} 页 · 共 {{ total }} 条</span>
</div>
{% endif %}
</body>
</html>"""

SEC_DETAIL_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ filing.ticker }} · {{ filing.form }}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e6edf3;font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;max-width:1280px;margin:0 auto;padding:28px 22px}
a{color:#58a6ff;text-decoration:none}
.back{margin-bottom:16px}
.back a{color:#8b949e;font-size:13px}
.back a:hover{color:#e6edf3}
h1{font-size:20px;color:#f0f6fc;font-weight:600;border-bottom:1px solid #30363d;padding-bottom:12px;margin-bottom:8px}
.meta{color:#8b949e;font-size:13px;margin-bottom:10px}
.summary{color:#e6edf3;font-size:15px;font-weight:600;background:#161b22;border:1px solid #21262d;border-radius:6px;padding:12px 16px;margin-bottom:20px}
.doc{margin-bottom:24px}
.doc h3{color:#f0f6fc;font-size:13px;font-weight:600;margin-bottom:8px;border-bottom:1px solid #21262d;padding-bottom:6px}
.doc pre{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:16px;font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word;color:#c9d1d9;max-height:70vh;overflow:auto}
@media (max-width:640px){body{padding:18px 12px}h1{font-size:17px}}
</style>
</head>
<body>
<div class="back"><a href="/sec">← 返回 SEC 列表</a></div>
<h1>${{ filing.ticker }} — {{ filing.company or filing.ticker }} · {{ filing.form }}</h1>
<div class="meta">📅 {{ filing.display_when or filing.acceptance_et or filing.filing_date }} · <a href="{{ filing.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a></div>
{% if filing.llm_summary or filing.summary %}<div class="summary">📌 {{ filing.llm_summary or filing.summary }}</div>{% endif %}
{% for d in docs %}
<div class="doc">
  <h3>{{ d.filename }} <span style="color:#8b949e;font-weight:400">({{ d.role }})</span></h3>
  {% if d.text %}<pre>{{ d.text }}</pre>{% else %}<pre style="color:#8b949e">(无提取文本 — 请查看 SEC 原文)</pre>{% endif %}
</div>
{% endfor %}
</body>
</html>"""


@app.route("/", methods=["GET"])
def index():
    if "user" not in session:
        return redirect("/login")
    cat = request.args.get("cat", "daily")
    if cat not in ("daily", "weekly", "ishares", "crypto", "ai_daily_recap", "macro_events"):
        cat = "daily"
    reports = list_reports(cat)
    return render_template_string(INDEX_HTML, cat=cat, reports=reports)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        if username == USERNAME and pw_hash == PASSWORD_HASH:
            session["user"] = username
            session.permanent = request.form.get("remember") == "1"
            return redirect("/")
        error = "用户名或密码错误"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/view/<category>/<filename>")
def view_report(category, filename):
    if "user" not in session:
        return redirect("/login")
    if category not in ("daily", "weekly", "ishares", "crypto", "ai_daily_recap", "macro_events"):
        return "invalid category", 404
    content = read_report(category, filename)
    if content is None:
        return "not found", 404
    title = filename.replace(".md", "")
    # Try extract first heading
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    html = md_to_html(content)
    # Wrap markdown tables in a scrollable container (mobile-friendly horizontal scroll)
    html = re.sub(r"<table>", '<div class="tbl-wrap"><table>', html)
    html = re.sub(r"</table>", "</table></div>", html)
    return render_template_string(REPORT_HTML, title=title, content=html, cat=category)


def _clean_html(s: str, limit: int = 240) -> str:
    """Strip HTML tags/entities from a raw news excerpt into a clean plain-text line."""
    if not s:
        return ""
    s = html.unescape(str(s))
    s = re.sub(r"<\s*/?[a-zA-Z!][^>]*>?", " ", s)  # drop tags (incl. unclosed)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[: limit].rstrip() + "…"
    return s


def news_eff_ts(n: dict) -> str:
    """Effective sortable timestamp for a news item (published date, else capture time)."""
    return n.get("published_ts") or n.get("captured_at") or ""


def _ts_after(ts_str: str, cutoff: datetime) -> bool:
    try:
        return datetime.fromisoformat(ts_str) >= cutoff
    except Exception:
        return False


HKT_TZ = timezone(timedelta(hours=8))


def to_hkt(ts_str: str) -> str:
    """ISO 8601 timestamp -> 'YYYY-MM-DD HH:MM HKT' (UTC+8). Naive ts treated as UTC."""
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(HKT_TZ).strftime("%Y-%m-%d %H:%M HKT")
    except Exception:
        return ""


def filing_hkt(f: dict) -> str:
    """Filing acceptance time in HKT; fallback: parse 'YYYY-MM-DD HH:MM ET', else filing_date."""
    h = to_hkt(f.get("acceptance_datetime") or "")
    if h:
        return h
    et = f.get("acceptance_et") or ""
    m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) ET", et)
    if m:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo("America/New_York"))
            return dt.astimezone(HKT_TZ).strftime("%Y-%m-%d %H:%M HKT")
        except Exception:
            # EDT = UTC-4; close enough when zoneinfo unavailable
            return f"{m.group(1)} {m.group(2)} +12h (HKT)"
    return f.get("filing_date") or ""


@app.route("/sec")
def sec_index():
    if "user" not in session:
        return redirect("/login")
    filings = load_sec_filings()
    llm = load_llm_summaries()
    for f in filings:
        f["llm_summary"] = llm.get(f.get("accession"), "")
        f["display_when"] = filing_hkt(f)
        if is_insider_form(f.get("form", "")):
            # Form 3/4/5 machine summary already has name/role/transaction detail
            f["display_summary"] = f["llm_summary"] or f.get("summary", "")
        else:
            # else: fall back to a clean excerpt of the actual filing text
            f["display_summary"] = f["llm_summary"] or _clean_html(f.get("excerpt", ""), 300)
    news = load_news()
    news_llm = load_news_llm_summaries()
    for n in news:
        n["llm_summary"] = news_llm.get(n.get("url"), "")
        n["clean_summary"] = _clean_html(n.get("summary", ""))
        n["display_date"] = ""
        n["is_capture_date"] = False
        ts = n.get("published_ts")
        if ts and to_hkt(ts):
            n["display_date"] = to_hkt(ts)
        else:
            ca = n.get("captured_at")
            if ca and to_hkt(ca):
                n["display_date"] = to_hkt(ca)
                n["is_capture_date"] = True
    stype = request.args.get("type", "news")
    range_param = request.args.get("range", "24h")
    ticker_param = request.args.get("ticker", "").strip().upper()
    material = [f for f in filings if not is_insider_form(f.get("form", ""))]
    insider = [f for f in filings if is_insider_form(f.get("form", ""))]
    n_news_total = len(news)
    n_material = len(material)
    n_insider = len(insider)

    if stype == "insider":
        shown = insider
    elif stype == "material":
        shown = material
    else:
        # sort news: date/time desc, then company/ticker desc
        news = sorted(news, key=lambda n: (news_eff_ts(n), (n.get("ticker") or "").upper()), reverse=True)
        if ticker_param:
            news = [n for n in news if (n.get("ticker") or "").upper() == ticker_param]
        hours = {"24h": 24, "7d": 168, "30d": 720}.get(range_param)
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            news = [n for n in news if _ts_after(news_eff_ts(n), cutoff)]
        shown = news

    all_tickers = sorted({(n.get("ticker") or "") for n in load_news()} | {(f.get("ticker") or "") for f in filings})
    all_tickers = [t for t in all_tickers if t]

    per_page = 100
    total = len(shown)
    total_pages = max(1, (total + per_page - 1) // per_page)
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = max(1, min(page, total_pages))
    page_items = shown[(page - 1) * per_page: page * per_page]

    return render_template_string(
        SEC_INDEX_HTML, items=page_items, form_class=form_class, stype=stype,
        n_news=n_news_total, n_material=n_material, n_insider=n_insider,
        page=page, total_pages=total_pages, total=total,
        range_param=range_param, ticker_param=ticker_param, all_tickers=all_tickers,
    )


@app.route("/sec/<accession>")
def sec_detail(accession):
    if "user" not in session:
        return redirect("/login")
    filings = load_sec_filings()
    filing = next((f for f in filings if f.get("accession") == accession), None)
    if filing is None:
        return "not found", 404
    filing["llm_summary"] = load_llm_summaries().get(filing.get("accession"), "")
    filing["display_when"] = filing_hkt(filing)
    docs = filing_documents(filing)
    return render_template_string(SEC_DETAIL_HTML, filing=filing, docs=docs)


SYSTEM_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>System Monitor</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f1117;color:#e6edf3;font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;max-width:1280px;margin:0 auto;padding:28px 22px}
a{color:#58a6ff;text-decoration:none}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #30363d}
.header h1{font-size:19px;color:#f0f6fc;font-weight:600}
.header a{color:#8b949e;font-size:13px}
.header a:hover{color:#e6edf3}
.sub{color:#8b949e;font-size:12.5px;margin-bottom:22px}
h2{color:#f0f6fc;font-size:16px;margin:26px 0 12px;border-bottom:1px solid #21262d;padding-bottom:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.card{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px 18px}
.card h3{font-size:13px;color:#8b949e;font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:.4px}
.metric{display:flex;justify-content:space-between;font-size:13.5px;padding:3px 0}
.metric .v{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#e6edf3}
.bar{background:#0d1117;border-radius:4px;height:10px;margin-top:10px;overflow:hidden;display:flex}
.bar .seg{height:100%}
.seg.used{background:#238636}.seg.warn{background:#d29922}.seg.bad{background:#da3633}.seg.free{background:#30363d;width:100%}
.bar:hover .legend,.legend{display:flex;font-size:11px;color:#8b949e;margin-top:5px;gap:12px}
.legend i{width:8px;height:8px;border-radius:2px;display:inline-block;margin-right:4px}
table{border-collapse:collapse;width:100%;margin-top:4px;font-size:13px}
th,td{border-bottom:1px solid #21262d;padding:7px 10px;text-align:left;vertical-align:middle}
th{color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:.3px;position:sticky;top:0;background:#0f1117}
tr:hover td{background:#161b22}
td.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#c9d1d9;white-space:nowrap}
.pbar{background:#0d1117;border-radius:3px;height:7px;min-width:80px;overflow:hidden}
.pbar>div{height:100%;border-radius:3px}
.tag{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:8px;background:#1f6feb;color:#fff}
.tag.sys{background:#30363d;color:#8b949e}
.swap-note{font-size:12px;color:#d29922;margin-top:6px}
@media (max-width:640px){body{padding:18px 12px}th:nth-child(n+6),td:nth-child(n+6){display:none}}
</style>
</head>
<body>
<div class="header">
  <h1>🖥️ 系统监控</h1>
  <a href="/">← 返回</a>
</div>
<div class="sub">刷新于 {{ gen_time }} HKT · 每 30 秒自动刷新 · 数据源 /proc + df</div>

<h2>📊 总体</h2>
<div class="cards">
  <div class="card">
    <h3>内存</h3>
    {% for m in mem_rows %}
    <div class="metric"><span>{{ m.label }}</span><span class="v">{{ m.value }}</span></div>
    {% endfor %}
    <div class="bar">
      <div class="seg {{ mem_state }}" style="width:{{ mem_pct }}%"></div>
      <div class="seg free"></div>
    </div>
    <div class="legend"><i class="seg used"></i>{{ mem_pct }}% 已用</div>
  </div>
  <div class="card">
    <h3>Swap</h3>
    {% for m in swap_rows %}
    <div class="metric"><span>{{ m.label }}</span><span class="v">{{ m.value }}</span></div>
    {% endfor %}
    <div class="bar">
      <div class="seg warn" style="width:{{ swap_pct }}%"></div>
      <div class="seg free"></div>
    </div>
    <div class="legend"><i class="seg warn"></i>{{ swap_pct }}% 已用{% if swap_high %}<span class="swap-note">⚠ 内存压力大，进程被挤到 swap</span>{% endif %}</div>
  </div>
  <div class="card">
    <h3>磁盘</h3>
    {% for d in disks %}
    <div class="metric"><span>{{ d.mount }} <small style="color:#8b949e">({{ d.fstype }})</small></span><span class="v">{{ d.used_h }} / {{ d.size_h }} · {{ d.pct }}%</span></div>
    <div class="pbar"><div style="width:{{ d.pct }}%;background:{% if d.pct > 85 %}#da3633{% elif d.pct > 70 %}#d29922{% else %}#238636{% endif %}"></div></div>
    {% endfor %}
  </div>
  <div class="card">
    <h3>CPU / 负载</h3>
    <div class="metric"><span>核心数</span><span class="v">{{ ncpu }}</span></div>
    <div class="metric"><span>负载 1/5/15 min</span><span class="v">{{ load1 }} / {{ load5 }} / {{ load15 }}</span></div>
    <div class="metric"><span>CPU 使用率</span><span class="v">{{ cpu_pct }}%</span></div>
    <div class="pbar"><div style="width:{{ cpu_pct }}%;background:{% if cpu_pct > 80 %}#da3633{% elif cpu_pct > 50 %}#d29922{% else %}#238636{% endif %}"></div></div>
    <div class="metric" style="margin-top:8px"><span>运行时间</span><span class="v">{{ uptime }}</span></div>
    <div class="metric"><span>进程数</span><span class="v">{{ nprocs }}</span></div>
  </div>
</div>

<h2>⚙️ 进程明细 — 按内存排序 Top {{ procs|length }}</h2>
<table>
<thead><tr><th>PID</th><th>用户</th><th>程序</th><th>说明</th><th>内存</th><th>%MEM</th><th>CPU%</th><th>启动时长</th></tr></thead>
<tbody>
{% for p in procs %}
<tr>
  <td class="mono">{{ p.pid }}</td>
  <td>{{ p.user }}</td>
  <td class="mono">{{ p.comm }}</td>
  <td style="color:#8b949e;font-size:12px">{{ p.args }}</td>
  <td class="mono">{{ p.rss_h }}</td>
  <td class="mono">
    <div class="pbar"><div style="width:{{ [p.mem_pct * 20, 100]|min }}%;background:{% if p.mem_pct > 8 %}#da3633{% elif p.mem_pct > 3 %}#d29922{% else %}#238636{% endif %}"></div></div>
    <span style="font-size:11.5px;color:#8b949e">{{ p.mem_pct }}%</span>
  </td>
  <td class="mono">{{ p.cpu_pct }}</td>
  <td class="mono">{{ p.etime }}</td>
</tr>
{% endfor %}
</tbody>
</table>

</body>
</html>"""


def _human_bytes(mb: float) -> str:
    if mb >= 1024 * 1024:
        return f"{mb / 1024 / 1024:.2f} TB"
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"


def read_meminfo() -> dict:
    out = {}
    for line in open("/proc/meminfo"):
        k, _, rest = line.partition(":")
        parts = rest.split()
        out[k.strip()] = int(parts[0]) if parts and parts[0].isdigit() else 0   # kB
    return out


def _pretty_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{days}天 {hours}时 {mins}分"


def collect_procs(sort_key: str = "rss", limit: int = 40) -> list:
    """Top processes by memory (or cpu), parsed from ps for portability."""
    import subprocess
    try:
        raw = subprocess.run(
            ["ps", "-eo",
             "pid=PID,user=USER,pcpu=PCPU,pmem=PMEM,rss=RSS,etimes=ETIMES,comm:32=COMM,args=ARGS",
             "--sort=-rss"],
            capture_output=True, text=True, timeout=10)
        lines = raw.stdout.splitlines()
    except Exception:
        return []
    rows = []
    for l in lines[1:]:                 # skip header line
        parts = l.split(None, 7)        # PID USER PCPU PMEM RSS ETIMES COMM ARGS
        if len(parts) < 7:
            continue
        args_full = parts[7] if len(parts) == 8 else ""
        try:
            et_s = int(parts[5])
            etime = f"{et_s//86400}d {et_s%86400//3600}h {(et_s%3600)//60}m" if et_s >= 3600 else \
                    f"{et_s//60}m" if et_s >= 60 else f"{et_s}s"
            rows.append({
                "pid": parts[0], "user": parts[1],
                "cpu_pct": float(parts[2]), "mem_pct": float(parts[3]),
                "rss_kb": int(parts[4]), "rss_h": _human_bytes(int(parts[4]) / 1024),
                "etime": etime,
                "comm": parts[6], "args": args_full[:90],
            })
        except ValueError:
            continue
    key = ("cpu_pct" if sort_key.lstrip("-") == "cpu" else "rss_kb")
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows[:limit]


@app.route("/system")
def system_page():
    if "user" not in session:
        return redirect("/login")
    mi = read_meminfo()
    total_mb = mi.get("MemTotal", 0) / 1024
    avail_mb = mi.get("MemAvailable", 0) / 1024
    used_mb = total_mb - avail_mb
    mem_pct = round(used_mb / total_mb * 100, 1) if total_mb else 0

    sw_total = mi.get("SwapTotal", 0) / 1024
    sw_free = mi.get("SwapFree", 0) / 1024
    sw_used = sw_total - sw_free
    swap_pct = round(sw_used / sw_total * 100, 1) if sw_total else 0

    disks = []
    for path in ("/",):
        st = os.statvfs(path)
        size_gb = st.f_blocks * st.f_frsize / 1024**3
        free_gb = st.f_bavail * st.f_frsize / 1024**3
        used_gb = size_gb - free_gb
        pct = round(used_gb / size_gb * 100, 1) if size_gb else 0
        disks.append({"mount": path, "fstype": "xfs",
                      "size_h": f"{size_gb:.0f}G", "used_h": f"{used_gb:.0f}G",
                      "free_h": f"{free_gb:.0f}G", "pct": pct})

    load1, load5, load15 = os.getloadavg()
    ncpu = os.cpu_count() or 1
    cpu_pct = min(100, round(load1 / ncpu * 100))
    up_s = None
    try:
        with open("/proc/uptime") as f:
            up_s = float(f.read().split()[0])
    except Exception:
        pass

    procs = collect_procs("rss", 40)

    return render_template_string(SYSTEM_HTML,
        gen_time=datetime.now(HKT_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        mem_rows=[
            {"label": "总量", "value": _human_bytes(total_mb)},
            {"label": "已用 (used = total − available)", "value": _human_bytes(used_mb)},
            {"label": "可用(available)", "value": _human_bytes(avail_mb)},
            {"label": "buff/cache", "value": _human_bytes((mi.get('Buffers', 0) + mi.get('Cached', 0)) / 1024)},
        ],
        mem_pct=min(100, mem_pct),
        mem_state="bad" if mem_pct > 85 else ("warn" if mem_pct > 70 else "used"),
        swap_rows=[
            {"label": "总量", "value": _human_bytes(sw_total)},
            {"label": "已用", "value": _human_bytes(sw_used)},
        ],
        swap_pct=swap_pct, swap_high=swap_pct > 60,
        disks=disks,
        ncpu=ncpu, load1=load1, load5=load5, load15=load15,
        cpu_pct=cpu_pct,
        uptime=_pretty_uptime(up_s) if up_s else "-",
        nprocs=sum(1 for _ in os.listdir("/proc") if _.isdigit()),
        procs=procs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8686, debug=False)
