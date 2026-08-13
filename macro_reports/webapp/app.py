#!/usr/bin/env python3
"""Macro Reports Viewer — Simple Flask webapp with login."""

import os, re, hashlib, secrets, json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, session, url_for
import markdown2

BASE_DIR = "/root/projects/macro_reports"
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Single user credentials
USERNAME = "bear"
PASSWORD_HASH = hashlib.sha256("bear2026".encode()).hexdigest()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


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


def load_sec_filings() -> list:
    """Load the persisted SEC filings index (newest first)."""
    try:
        with open(SEC_FILINGS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


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
  max-width:900px;margin:0 auto;padding:24px 20px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;
  padding-bottom:16px;border-bottom:1px solid #30363d}
.header h1{font-size:18px;color:#f0f6fc}
.header a{color:#8b949e;text-decoration:none;font-size:13px}
.header a:hover{color:#e1e4e8}
.cats{display:flex;gap:8px;margin-bottom:24px}
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
  <a href="/?cat=ashare" class="{{ 'active' if cat=='ashare' else '' }}">🇨🇳 A股</a>
  <a href="/?cat=ai_daily_recap" class="{{ 'active' if cat=='ai_daily_recap' else '' }}">AI Daily Recap</a>
  <a href="/?cat=ai_premarket" class="{{ 'active' if cat=='ai_premarket' else '' }}">AI Pre-Market</a>
  <a href="/sec">📄 SEC Filings</a>
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
  max-width:900px;margin:0 auto;padding:24px 20px}
.back{margin-bottom:16px}
.back a{color:#8b949e;text-decoration:none;font-size:13px}
.back a:hover{color:#58a6ff}
h1,h2,h3,h4{color:#f0f6fc;margin:24px 0 12px}
h1{font-size:22px;border-bottom:1px solid #30363d;padding-bottom:12px}
h2{font-size:18px}
h3{font-size:15px;color:#e1e4e8}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}
th,td{border:1px solid #30363d;padding:8px 12px;text-align:left}
th{background:#161b22;color:#f0f6fc;font-weight:600}
tr:hover{background:#161b22}
a{color:#58a6ff}
code{background:#161b22;padding:2px 6px;border-radius:3px;font-size:13px}
ul,ol{padding-left:24px;margin:8px 0}
li{margin:4px 0}
hr{border:none;border-top:1px solid #30363d;margin:24px 0}
blockquote{border-left:3px solid #30363d;padding:4px 16px;margin:12px 0;color:#8b949e}
strong{color:#f0f6fc}
img{max-width:100%}
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
body{background:#0f1117;color:#e1e4e8;font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;padding:24px 20px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #30363d}
.header h1{font-size:18px;color:#f0f6fc}
.header a{color:#8b949e;text-decoration:none;font-size:13px}
.header a:hover{color:#e1e4e8}
.sub{color:#8b949e;font-size:12px;margin-bottom:20px}
.sub a{color:#58a6ff}
.filing{border:1px solid #21262d;border-radius:6px;padding:16px;margin-bottom:12px;background:#161b22}
.filing .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:8px;flex-wrap:wrap}
.filing .tick{color:#f0f6fc;font-weight:600;font-size:15px}
.filing .form{background:#238636;color:#fff;padding:1px 8px;border-radius:4px;font-size:12px;font-weight:600}
.filing .meta{color:#8b949e;font-size:12px}
.filing .reason{color:#e1e4e8;font-size:12px;margin-bottom:6px}
.filing .excerpt{color:#8b949e;font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word;max-height:120px;overflow:hidden;border-left:3px solid #30363d;padding-left:12px;margin:8px 0}
.filing .links a{color:#58a6ff;text-decoration:none;font-size:12px;margin-right:16px}
.filing .links a:hover{text-decoration:underline}
.empty{text-align:center;color:#8b949e;padding:48px 0}
</style>
</head>
<body>
<div class="header">
  <h1>📄 SEC Filings</h1>
  <a href="/">← 返回</a>
</div>
<div class="sub">共 {{ filings|length }} 份文件 · 数据源 <a href="https://www.sec.gov/edgar" target="_blank" rel="noopener">SEC EDGAR</a> · 「🔗 SEC 原文」跳转官方原文</div>
{% if filings %}
{% for f in filings %}
<div class="filing">
  <div class="top">
    <span class="tick">${{ f.ticker }} — {{ f.company or f.ticker }}</span>
    <span><span class="form">{{ f.form }}</span><span class="meta"> · {{ f.filing_date }}{% if f.acceptance_et %} · {{ f.acceptance_et }}{% endif %}{% if f.sector %} · {{ f.sector }}{% endif %}</span></span>
  </div>
  {% if f.reason_summary %}<div class="reason">{{ f.reason_summary }}</div>{% endif %}
  {% if f.excerpt %}<div class="excerpt">{{ f.excerpt[:400] }}{% if f.excerpt|length > 400 %}…{% endif %}</div>{% endif %}
  <div class="links">
    <a href="/sec/{{ f.accession }}">📖 全文</a>
    <a href="{{ f.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a>
  </div>
</div>
{% endfor %}
{% else %}
<div class="empty">暂无 SEC 文件</div>
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
body{background:#0f1117;color:#e1e4e8;font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;padding:24px 20px}
.back{margin-bottom:16px}
.back a{color:#8b949e;text-decoration:none;font-size:13px}
.back a:hover{color:#58a6ff}
h1{font-size:20px;color:#f0f6fc;border-bottom:1px solid #30363d;padding-bottom:12px;margin-bottom:8px}
.meta{color:#8b949e;font-size:12px;margin-bottom:20px}
.meta a{color:#58a6ff}
.doc{margin-bottom:24px}
.doc h3{color:#f0f6fc;font-size:13px;margin-bottom:8px;border-bottom:1px solid #21262d;padding-bottom:6px}
.doc pre{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:16px;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word;color:#e1e4e8;max-height:70vh;overflow:auto}
</style>
</head>
<body>
<div class="back"><a href="/sec">← 返回 SEC 列表</a></div>
<h1>${{ filing.ticker }} — {{ filing.company or filing.ticker }} · {{ filing.form }}</h1>
<div class="meta">{{ filing.filing_date }}{% if filing.acceptance_et %} · {{ filing.acceptance_et }}{% endif %} · <a href="{{ filing.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a></div>
{% for d in docs %}
<div class="doc">
  <h3>{{ d.filename }} <span style="color:#8b949e">({{ d.role }})</span></h3>
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
    if cat not in ("daily", "weekly", "ishares", "crypto", "ashare", "ai_daily_recap", "ai_premarket"):
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
    if category not in ("daily", "weekly", "ishares", "crypto", "ai_daily_recap", "ai_premarket"):
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
    return render_template_string(REPORT_HTML, title=title, content=html, cat=category)


@app.route("/sec")
def sec_index():
    if "user" not in session:
        return redirect("/login")
    filings = load_sec_filings()
    return render_template_string(SEC_INDEX_HTML, filings=filings)


@app.route("/sec/<accession>")
def sec_detail(accession):
    if "user" not in session:
        return redirect("/login")
    filings = load_sec_filings()
    filing = next((f for f in filings if f.get("accession") == accession), None)
    if filing is None:
        return "not found", 404
    docs = filing_documents(filing)
    return render_template_string(SEC_DETAIL_HTML, filing=filing, docs=docs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8686, debug=False)
