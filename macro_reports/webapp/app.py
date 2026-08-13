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
LLM_SUMMARIES_PATH = os.path.join(SEC_DATA_DIR, "llm_summaries.jsonl")


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
body{background:#0f1117;color:#e6edf3;font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;max-width:920px;margin:0 auto;padding:28px 22px}
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
.pager{display:flex;align-items:center;gap:8px;margin:24px 0 8px;flex-wrap:wrap}
.pager .pg{padding:6px 12px;border-radius:6px;background:#161b22;border:1px solid #30363d;color:#8b949e;font-size:13px;text-decoration:none}
.pager .pg:hover{color:#e6edf3;border-color:#8b949e}
.pager .pg.cur{background:#238636;color:#fff;border-color:#238636;font-weight:600}
.pager .info{color:#8b949e;font-size:12.5px;margin-left:auto}
.filing{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:18px 20px;margin-bottom:14px}
.filing:hover{border-color:#30363d}
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
</style>
</head>
<body>
<div class="header">
  <h1>📄 SEC Filings</h1>
  <a href="/">← 返回</a>
</div>
<div class="tabs">
  <a href="/sec" class="{{ 'active' if stype=='material' else '' }}">📄 重要文件 ({{ n_material }})</a>
  <a href="/sec?type=insider" class="{{ 'active' if stype=='insider' else '' }}">👤 内部人交易 ({{ n_insider }})</a>
</div>
<div class="sub">数据源 <a href="https://www.sec.gov/edgar" target="_blank" rel="noopener">SEC EDGAR</a> · 「🔗 SEC 原文」跳转官方原文</div>
{% if filings %}
{% for f in filings %}
<div class="filing">
  <div class="f-head">
    <span class="tick">${{ f.ticker }}</span>
    <span class="company">{{ f.company or f.ticker }}</span>
    <span class="form {{ form_class(f.form) }}">{{ f.form }}</span>
  </div>
  <div class="f-when">{{ f.acceptance_et or f.filing_date }}{% if f.sector %} · {{ f.sector }}{% endif %}</div>
  {% if f.llm_summary or f.summary %}<div class="f-summary">{{ f.llm_summary or f.summary }}</div>{% endif %}
  <div class="f-links">
    <a href="/sec/{{ f.accession }}">📖 全文</a>
    <a href="{{ f.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a>
  </div>
</div>
{% endfor %}
{% else %}
<div class="empty">暂无 SEC 文件</div>
{% endif %}
{% if total_pages > 1 %}
<div class="pager">
  {% if page > 1 %}<a class="pg" href="/sec?type={{ stype }}&page={{ page - 1 }}">‹ 上一页</a>{% endif %}
  {% for p in range(1, total_pages + 1) %}
    {% if p == page %}<span class="pg cur">{{ p }}</span>{% else %}<a class="pg" href="/sec?type={{ stype }}&page={{ p }}">{{ p }}</a>{% endif %}
  {% endfor %}
  {% if page < total_pages %}<a class="pg" href="/sec?type={{ stype }}&page={{ page + 1 }}">下一页 ›</a>{% endif %}
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
body{background:#0f1117;color:#e6edf3;font:15px/1.7 -apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;max-width:920px;margin:0 auto;padding:28px 22px}
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
</style>
</head>
<body>
<div class="back"><a href="/sec">← 返回 SEC 列表</a></div>
<h1>${{ filing.ticker }} — {{ filing.company or filing.ticker }} · {{ filing.form }}</h1>
<div class="meta">{{ filing.acceptance_et or filing.filing_date }} · <a href="{{ filing.index_url }}" target="_blank" rel="noopener">🔗 SEC 原文 ↗</a></div>
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
    llm = load_llm_summaries()
    for f in filings:
        f["llm_summary"] = llm.get(f.get("accession"), "")
    stype = request.args.get("type", "material")
    material = [f for f in filings if not is_insider_form(f.get("form", ""))]
    insider = [f for f in filings if is_insider_form(f.get("form", ""))]
    shown = insider if stype == "insider" else material

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
        SEC_INDEX_HTML, filings=page_items, form_class=form_class, stype=stype,
        n_material=len(material), n_insider=len(insider),
        page=page, total_pages=total_pages, total=total,
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
    docs = filing_documents(filing)
    return render_template_string(SEC_DETAIL_HTML, filing=filing, docs=docs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8686, debug=False)
