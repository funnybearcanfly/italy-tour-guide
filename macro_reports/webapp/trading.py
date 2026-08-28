#!/usr/bin/env python3
"""Hyperliquid 交易追踪 — Flask Blueprint。

考察单位是 order（Hyperliquid 的 oid），一个 order 可能被拆成多个 trade（fill）执行。
数据全部来自 Hyperliquid Info API（程序化，无 LLM）：
  - userFills       : 成交明细（增量入库，按 tid 去重）
  - clearinghouseState : 账户状态（价格刷新时更新持仓市值/未实现盈亏/杠杆）
  - metaAndAssetCtxs: 全市场标记价（用于未实现盈亏估值）

SQLite 表：
  hl_fills   原始成交（tid 唯一）
  hl_orders  order 聚合结果（oid 唯一，由 sync 重建受影响 order）
  hl_notes   order 的交易想法/复盘笔记（手工录入）
  hl_account 账户状态快照（每次价格刷新一行）
"""

import json
import os
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template_string, request, session, url_for

HL_API = "https://api.hyperliquid.xyz/info"
DEFAULT_ADDRESS = "0x882b51825750a0D5A0B2cE2CA410Ad27C6ebD4b5"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "trading.db")

bp = Blueprint("trading", __name__)


# ---------------------------------------------------------------- helpers

def _db() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _hl_post(payload: dict) -> dict:
    req = urllib.request.Request(
        HL_API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable: HL request retries exhausted")


def _address() -> str:
    return (request.args.get("addr") or DEFAULT_ADDRESS).strip()


def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- schema

SCHEMA = """
CREATE TABLE IF NOT EXISTS hl_fills (
  tid INTEGER PRIMARY KEY,
  oid INTEGER NOT NULL,
  coin TEXT NOT NULL,
  px REAL NOT NULL,
  sz REAL NOT NULL,
  side TEXT NOT NULL,
  dir TEXT NOT NULL,
  time INTEGER NOT NULL,
  closed_pnl REAL NOT NULL DEFAULT 0,
  fee REAL NOT NULL DEFAULT 0,
  fee_token TEXT,
  crossed INTEGER,
  liquidation INTEGER NOT NULL DEFAULT 0,
  hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_fills_oid ON hl_fills(oid);
CREATE INDEX IF NOT EXISTS idx_fills_time ON hl_fills(time);

CREATE TABLE IF NOT EXISTS hl_orders (
  oid INTEGER PRIMARY KEY,
  coin TEXT NOT NULL,
  side TEXT NOT NULL,            -- Open Long / Open Short / 原始首笔 dir
  opened_at INTEGER NOT NULL,
  last_fill_at INTEGER NOT NULL,
  n_fills INTEGER NOT NULL,
  filled_sz REAL NOT NULL,       -- 带符号净成交量（B=+, A=-）
  notional_usd REAL NOT NULL,    -- sum(px*|sz|)
  avg_px REAL,                   -- 成交均价
  closed_pnl REAL NOT NULL DEFAULT 0,
  fees REAL NOT NULL DEFAULT 0,
  n_liquidations INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_orders_time ON hl_orders(opened_at);

CREATE TABLE IF NOT EXISTS hl_notes (
  oid INTEGER PRIMARY KEY,
  idea TEXT NOT NULL DEFAULT '',       -- 开仓时的交易想法
  review TEXT NOT NULL DEFAULT '',     -- 事后复盘
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS hl_account (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  fetched_at INTEGER,
  account_value REAL,
  total_ntl_pos REAL,
  margin_used REAL,
  unrealized_pnl REAL,
  leverage REAL,                 -- notional / account_value
  positions TEXT                 -- JSON
);
"""


def _init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)


# ---------------------------------------------------------------- sync

def _rebuild_order(conn: sqlite3.Connection, oid: int):
    """由该 oid 的全部 fills 重建 hl_orders 行（order 是考察单位）。"""
    fills = conn.execute("SELECT * FROM hl_fills WHERE oid=? ORDER BY time, tid", (oid,)).fetchall()
    if not fills:
        conn.execute("DELETE FROM hl_orders WHERE oid=?", (oid,))
        return
    signed = 0.0
    notional = 0.0
    closed_pnl = 0.0
    fees = 0.0
    liqs = 0
    for f in fills:
        sz = f["sz"] * (1 if f["side"] == "B" else -1)
        signed += sz
        notional += abs(sz) * f["px"]
        closed_pnl += f["closed_pnl"]
        fees += f["fee"]
        liqs += 1 if f["liquidation"] else 0
    conn.execute(
        """INSERT INTO hl_orders (oid, coin, side, opened_at, last_fill_at, n_fills,
               filled_sz, notional_usd, avg_px, closed_pnl, fees, n_liquidations)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(oid) DO UPDATE SET
             coin=excluded.coin, side=excluded.side, opened_at=excluded.opened_at,
             last_fill_at=excluded.last_fill_at, n_fills=excluded.n_fills,
             filled_sz=excluded.filled_sz, notional_usd=excluded.notional_usd,
             avg_px=excluded.avg_px, closed_pnl=excluded.closed_pnl, fees=excluded.fees,
             n_liquidations=excluded.n_liquidations""",
        (
            oid, fills[0]["coin"], fills[0]["dir"], fills[0]["time"], fills[-1]["time"],
            len(fills), signed, notional,
            abs(notional / signed) if signed else None,
            closed_pnl, fees, liqs,
        ),
    )


def sync_fills(address: str | None = None) -> dict:
    """增量拉取 userFills，按 tid 去重入库，重建受影响 order 的聚合。"""
    address = address or DEFAULT_ADDRESS
    resp = _hl_post({"type": "userFills", "user": address})
    conn = _db()
    try:
        _init_db(conn)
        new_tids = 0
        touched_oids = set()
        for f in resp:
            cur = conn.execute(
                """INSERT OR IGNORE INTO hl_fills
                   (tid, oid, coin, px, sz, side, dir, time, closed_pnl, fee, fee_token,
                    crossed, liquidation, hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f["tid"], f["oid"], f["coin"], float(f["px"]), float(f["sz"]),
                    f["side"], f["dir"], f["time"], float(f.get("closedPnl") or 0),
                    float(f.get("fee") or 0), f.get("feeToken"),
                    1 if f.get("crossed") else 0,
                    1 if f.get("liquidation") else 0, f.get("hash"),
                ),
            )
            if cur.rowcount:
                new_tids += 1
                touched_oids.add(f["oid"])
        for oid in touched_oids:
            _rebuild_order(conn, oid)
        conn.commit()
        return {
            "ok": True,
            "fetched": len(resp),
            "new_fills": new_tids,
            "touched_orders": len(touched_oids),
        }
    finally:
        conn.close()


def refresh_prices(address: str | None = None) -> dict:
    """拉账户状态 + 全市场标记价，更新持仓未实现盈亏与整体杠杆。"""
    address = address or DEFAULT_ADDRESS
    state = _hl_post({"type": "clearinghouseState", "user": address})
    meta = _hl_post({"type": "metaAndAssetCtxs", "user": address})
    marks = {}
    try:
        universe, ctxs = meta[0]["universe"], meta[1]
        for name, ctx in zip([u["name"] for u in universe], ctxs):
            if ctx.get("markPx"):
                marks[name] = float(ctx["markPx"])
    except (KeyError, IndexError, TypeError):
        pass

    positions = []
    for ap in state.get("assetPositions", []):
        p = ap.get("position", {})
        szi = float(p.get("szi") or 0)
        if szi == 0:
            continue
        coin = p["coin"]
        mark = marks.get(coin) or float(p.get("entryPx") or 0)
        pos_val = abs(szi) * mark
        positions.append({
            "coin": coin,
            "szi": szi,
            "entry_px": float(p.get("entryPx") or 0),
            "mark_px": mark,
            "position_value": pos_val,
            "unrealized_pnl": float(p.get("unrealizedPnl") or 0),
            "leverage": p.get("leverage", {}),
            "margin_used": float(p.get("marginUsed") or 0),
            "liquidation_px": p.get("liquidationPx"),
            "roi": float(p.get("returnOnEquity") or 0),
            "cum_funding": float((p.get("cumFunding") or {}).get("allTime") or 0),
        })

    ms = state.get("marginSummary", {})
    account_value = float(ms.get("accountValue") or 0)
    total_ntl = float(ms.get("totalNtlPos") or 0)
    margin_used = float(ms.get("totalMarginUsed") or 0)
    unreal = sum(p["unrealized_pnl"] for p in positions)

    conn = _db()
    try:
        _init_db(conn)
        conn.execute(
            """INSERT INTO hl_account (id, fetched_at, account_value, total_ntl_pos,
                   margin_used, unrealized_pnl, leverage, positions)
               VALUES (1,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET fetched_at=excluded.fetched_at,
                 account_value=excluded.account_value, total_ntl_pos=excluded.total_ntl_pos,
                 margin_used=excluded.margin_used, unrealized_pnl=excluded.unrealized_pnl,
                 leverage=excluded.leverage, positions=excluded.positions""",
            (
                int(time.time() * 1000), account_value, total_ntl, margin_used,
                unreal, (total_ntl / account_value) if account_value else None,
                json.dumps(positions, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "account_value": account_value,
        "unrealized_pnl": unreal,
        "leverage": (total_ntl / account_value) if account_value else None,
        "n_positions": len(positions),
        "fetched_at": int(time.time() * 1000),
    }


# ---------------------------------------------------------------- queries

def _orders_with_notes(conn: sqlite3.Connection, limit: int = 500, offset: int = 0):
    rows = conn.execute(
        """SELECT o.*, n.idea, n.review,
                  (SELECT COUNT(*) FROM hl_fills f WHERE f.oid=o.oid) AS n_fills_check
           FROM hl_orders o LEFT JOIN hl_notes n ON n.oid = o.oid
           ORDER BY o.opened_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) c FROM hl_orders").fetchone()["c"]
    return rows, total


def _stats(conn: sqlite3.Connection) -> dict:
    acc = conn.execute("SELECT * FROM hl_account WHERE id=1").fetchone()
    agg = conn.execute(
        """SELECT COUNT(*) n_orders, SUM(closed_pnl) total_closed_pnl, SUM(fees) total_fees,
                  SUM(CASE WHEN closed_pnl>0 THEN 1 ELSE 0 END) wins,
                  SUM(CASE WHEN closed_pnl<0 THEN 1 ELSE 0 END) losses
           FROM hl_orders"""
    ).fetchone()
    n_notes = conn.execute(
        "SELECT COUNT(*) c FROM hl_notes WHERE idea != '' OR review != ''"
    ).fetchone()["c"]
    stats = dict(agg) if agg else {}
    stats["n_notes"] = n_notes
    stats["winrate"] = (
        stats["wins"] / (stats["wins"] + stats["losses"])
        if stats.get("wins") and (stats["wins"] + stats["losses"]) else None
    )
    if acc:
        stats["account"] = {
            "fetched_at": acc["fetched_at"],
            "account_value": acc["account_value"],
            "unrealized_pnl": acc["unrealized_pnl"],
            "leverage": acc["leverage"],
            "margin_used": acc["margin_used"],
            "positions": json.loads(acc["positions"] or "[]"),
        }
    else:
        stats["account"] = None
    return stats


# ---------------------------------------------------------------- routes

PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hyperliquid 交易追踪</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#0d1117; color:#e6edf3; margin:0; padding:16px; }
  a { color:#58a6ff; text-decoration:none; }
  .nav { margin-bottom:12px; font-size:14px; }
  h1 { font-size:20px; margin:8px 0; }
  h2 { font-size:16px; margin:20px 0 8px; }
  .cards { display:flex; flex-wrap:wrap; gap:10px; margin:12px 0; }
  .card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; min-width:140px; }
  .card .k { font-size:12px; color:#8b949e; }
  .card .v { font-size:18px; font-weight:600; margin-top:2px; }
  .pos { color:#3fb950; } .neg { color:#f85149; } .muted { color:#8b949e; }
  .btn { display:inline-block; background:#21262d; border:1px solid #30363d; color:#e6edf3;
         padding:6px 14px; border-radius:6px; cursor:pointer; font-size:13px; }
  .btn:hover { background:#30363d; }
  .btn.primary { background:#1f6feb; border-color:#1f6feb; color:#fff; }
  .tbl-wrap { overflow-x:auto; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th, td { border-bottom:1px solid #21262d; padding:6px 8px; text-align:right; white-space:nowrap; }
  th { color:#8b949e; font-weight:500; position:sticky; top:0; background:#0d1117; }
  td.l, th.l { text-align:left; }
  tr.order-row:hover { background:#161b22; cursor:pointer; }
  .badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11px; }
  .b-open { background:#1f6feb33; color:#58a6ff; }
  .b-close { background:#8b949e33; color:#8b949e; }
  .b-liq { background:#f8514933; color:#f85149; }
  .b-has-note { background:#23863633; color:#3fb950; }
  #detail { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px; margin-top:12px; display:none; }
  textarea { width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d;
             border-radius:6px; padding:8px; font-size:13px; min-height:70px; resize:vertical;
             font-family:inherit; }
  .lbl { font-size:12px; color:#8b949e; margin:10px 0 4px; }
  #msg { font-size:13px; margin-left:10px; }
  .sub { font-size:12px; color:#8b949e; margin:6px 0; }
  .posdet td { white-space:normal; }
  @media (max-width:640px){ .card{min-width:110px;} th,td{padding:5px 5px;} }
</style>
</head>
<body>
<div class="nav"><a href="/">← 返回</a></div>
<h1>📊 Hyperliquid 交易追踪</h1>
<div class="sub">地址 {{ address }} · 考察单位 = order（一笔 order 可含多笔 fill 成交）</div>

<div style="margin:10px 0">
  <button class="btn primary" onclick="doSync()">⬇ 同步成交</button>
  <button class="btn" onclick="doRefresh()">🔄 刷新价格/盈亏</button>
  <span id="msg" class="muted"></span>
</div>

{% if stats.account %}
<div class="cards">
  <div class="card"><div class="k">账户净值</div><div class="v">${{ "%.2f"|format(stats.account.account_value) }}</div></div>
  <div class="card"><div class="k">未实现盈亏</div>
    <div class="v {{ 'pos' if stats.account.unrealized_pnl >= 0 else 'neg' }}">{{ "%+.2f"|format(stats.account.unrealized_pnl) }}</div></div>
  <div class="card"><div class="k">整体杠杆</div><div class="v">{{ "%.1fx"|format(stats.account.leverage) if stats.account.leverage else "—" }}</div></div>
  <div class="card"><div class="k">占用保证金</div><div class="v">${{ "%.0f"|format(stats.account.margin_used) }}</div></div>
  <div class="card"><div class="k">已实现盈亏（全部 order）</div>
    <div class="v {{ 'pos' if stats.total_closed_pnl >= 0 else 'neg' }}">{{ "%+.2f"|format(stats.total_closed_pnl) }}</div></div>
  <div class="card"><div class="k">Order 数 / 胜率</div><div class="v">{{ stats.n_orders }} / {{ "%.0f%%"|format(stats.winrate*100) if stats.winrate is not none else "—" }}</div></div>
  <div class="card"><div class="k">手续费合计</div><div class="v">${{ "%.2f"|format(stats.total_fees) }}</div></div>
  <div class="card"><div class="k">已录入想法</div><div class="v">{{ stats.n_notes }} 个 order</div></div>
</div>
<div class="sub">快照时间：{{ ts_hkt }} (HKT) · 点击行展开 fills 与想法录入</div>

<h2>当前持仓</h2>
<div class="tbl-wrap"><table class="posdet">
<tr><th class="l">币种</th><th>方向</th><th>数量</th><th>开仓均价</th><th>标记价</th>
<th>市值</th><th>未实现盈亏</th><th>ROI</th><th>杠杆</th><th>强平价</th><th>累计资金费</th></tr>
{% for p in stats.account.positions %}
<tr>
  <td class="l">{{ p.coin }}</td>
  <td>{{ "多" if p.szi > 0 else "空" }}</td>
  <td>{{ "%.4g"|format(p.szi) }}</td>
  <td>{{ "%.6g"|format(p.entry_px) }}</td>
  <td>{{ "%.6g"|format(p.mark_px) }}</td>
  <td>${{ "%.0f"|format(p.position_value) }}</td>
  <td class="{{ 'pos' if p.unrealized_pnl >= 0 else 'neg' }}">{{ "%+.2f"|format(p.unrealized_pnl) }}</td>
  <td>{{ "%.2f%%"|format(p.roi*100) }}</td>
  <td>{{ p.leverage.value }}x{{ " (逐仓)" if p.leverage.type=="isolated" else "" }}</td>
  <td>{{ "%.6g"|format(p.liquidation_px|float) if p.liquidation_px else "—" }}</td>
  <td>{{ "%+.2f"|format(p.cum_funding) }}</td>
</tr>
{% endfor %}
</table></div>
{% endif %}

<h2>Order 历史（{{ stats.n_orders }}）</h2>
<div class="tbl-wrap"><table id="tbl">
<tr><th class="l">时间 (UTC)</th><th class="l">币种</th><th class="l">方向</th><th>fills</th>
<th>净成交量</th><th>均价</th><th>名义金额</th><th>已实现盈亏</th><th>手续费</th><th class="l">标签</th></tr>
{% for o in orders %}
<tr class="order-row" data-oid="{{ o.oid }}">
  <td class="l">{{ o.time_str }}</td>
  <td class="l">{{ o.coin }}</td>
  <td class="l">{{ o.side_str }}</td>
  <td>{{ o.n_fills }}</td>
  <td>{{ "%.6g"|format(o.filled_sz) }}</td>
  <td>{{ "%.6g"|format(o.avg_px) if o.avg_px else "—" }}</td>
  <td>${{ "%.0f"|format(o.notional_usd) }}</td>
  <td class="{{ 'pos' if o.closed_pnl >= 0 else 'neg' }}">{{ "%+.2f"|format(o.closed_pnl) }}</td>
  <td>{{ "%.2f"|format(o.fees) }}</td>
  <td class="l">
    {% if o.n_liquidations %}<span class="badge b-liq">清算</span>{% endif %}
    {% if o.idea %}<span class="badge b-has-note">有想法</span>{% endif %}
    {% if o.review %}<span class="badge b-has-note">有复盘</span>{% endif %}
  </td>
</tr>
{% endfor %}
</table></div>

<div id="detail">
  <div><b id="d-title"></b> <span id="d-meta" class="muted"></span></div>
  <div class="tbl-wrap"><table class="posdet" id="d-fills" style="margin-top:8px"></table></div>
  <div class="lbl">💡 交易想法（下单当时）</div>
  <textarea id="d-idea"></textarea>
  <div class="lbl">📝 事后复盘</div>
  <textarea id="d-review"></textarea>
  <div style="margin-top:10px">
    <button class="btn primary" onclick="saveNote()">保存</button>
    <button class="btn" onclick="document.getElementById('detail').style.display='none'">关闭</button>
    <span id="d-msg" class="muted"></span>
  </div>
</div>

<script>
const oidFills = {{ oid_fills_json | safe }};
let curOid = null;

async function doSync(){
  const m = document.getElementById('msg'); m.textContent = '同步中…';
  const r = await fetch('{{ url_for("trading.sync") }}').then(r=>r.json()).catch(e=>({error:String(e)}));
  m.textContent = r.ok ? `新增 ${r.new_fills} 笔成交 / ${r.touched_orders} 个 order` : ('失败: '+r.error);
  if(r.ok) setTimeout(()=>location.reload(), 800);
}
async function doRefresh(){
  const m = document.getElementById('msg'); m.textContent = '刷新价格中…';
  const r = await fetch('{{ url_for("trading.refresh") }}').then(r=>r.json()).catch(e=>({error:String(e)}));
  m.textContent = r.ok ? `净值 $${r.account_value.toFixed(2)} · 未实现 ${r.unrealized_pnl.toFixed(2)} · ${r.n_positions} 个持仓` : ('失败: '+r.error);
  if(r.ok) setTimeout(()=>location.reload(), 800);
}
function showDetail(oid){
  curOid = oid;
  const fills = oidFills[oid] || [];
  const first = fills[0] || {};
  document.getElementById('d-title').textContent = `Order ${oid} — ${first.coin||''}`;
  document.getElementById('d-meta').textContent = `${fills.length} 笔成交`;
  let h = '<tr><th class="l">时间</th><th>价格</th><th>数量</th><th class="l">方向</th><th>已实现盈亏</th><th>手续费</th></tr>';
  for(const f of fills){
    h += `<tr><td class="l">${f.time_str}</td><td>${f.px}</td><td>${f.sz}</td><td class="l">${f.dir}${f.liq?' <span style="color:#f85149">⚡清算</span>':''}</td><td>${f.pnl.toFixed(2)}</td><td>${f.fee.toFixed(4)}</td></tr>`;
  }
  document.getElementById('d-fills').innerHTML = h;
  document.getElementById('d-idea').value = first.idea || '';
  document.getElementById('d-review').value = first.review || '';
  document.getElementById('d-msg').textContent = '';
  const d = document.getElementById('detail');
  d.style.display = 'block';
  d.scrollIntoView({behavior:'smooth', block:'nearest'});
}
document.querySelectorAll('.order-row').forEach(tr => tr.addEventListener('click', () => showDetail(+tr.dataset.oid)));
async function saveNote(){
  if(curOid==null) return;
  const m = document.getElementById('d-msg'); m.textContent = '保存中…';
  const r = await fetch('{{ url_for("trading.save_note") }}', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({oid:curOid, idea:document.getElementById('d-idea').value, review:document.getElementById('d-review').value})
  }).then(r=>r.json()).catch(e=>({error:String(e)}));
  m.textContent = r.ok ? '✓ 已保存' : ('失败: '+r.error);
  if(r.ok) setTimeout(()=>location.reload(), 600);
}
</script>
</body>
</html>"""


def _fmt_side(o) -> str:
    d = (o["side"] or "")
    if d.startswith("Open Long"):
        return "开多"
    if d.startswith("Open Short"):
        return "开空"
    if "Long > Short" in d:
        return "多转空"
    if "Short > Long" in d:
        return "空转多"
    if d.startswith("Close"):
        return "平仓"
    return d


@bp.route("/trading")
def trading_page():
    if "user" not in session:
        return redirect("/login")
    address = _address()
    conn = _db()
    try:
        _init_db(conn)
        orders, total = _orders_with_notes(conn)
        stats = _stats(conn)
        orders = [dict(o) for o in orders]
        for o in orders:
            o["time_str"] = _ts(o["opened_at"])
            o["side_str"] = _fmt_side(o)
        oid_fills = {}
        for o in orders:
            fills = conn.execute(
                "SELECT * FROM hl_fills WHERE oid=? ORDER BY time, tid", (o["oid"],)
            ).fetchall()
            oid_fills[o["oid"]] = [{
                "time_str": _ts(f["time"]),
                "px": f["px"], "sz": f["sz"], "dir": f["dir"],
                "pnl": f["closed_pnl"], "fee": f["fee"], "liq": bool(f["liquidation"]),
                "idea": o["idea"] or "", "review": o["review"] or "",
            } for f in fills]
        import html as _html
        return render_template_string(
            PAGE,
            address=_html.escape(address),
            orders=orders,
            stats=stats,
            oid_fills_json=json.dumps(oid_fills, ensure_ascii=False),
            ts_hkt=datetime.fromtimestamp(stats["account"]["fetched_at"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if stats.get("account") else "",
        )
    finally:
        conn.close()


@bp.route("/trading/api/sync", methods=["POST"])
def sync():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(sync_fills(_address()))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/trading/api/refresh", methods=["POST"])
def refresh():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    try:
        return jsonify(refresh_prices(_address()))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@bp.route("/trading/api/note", methods=["POST"])
def save_note():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    oid = data.get("oid")
    if oid is None:
        return jsonify({"error": "oid required"}), 400
    conn = _db()
    try:
        _init_db(conn)
        conn.execute(
            """INSERT INTO hl_notes (oid, idea, review, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(oid) DO UPDATE SET idea=excluded.idea,
                 review=excluded.review, updated_at=excluded.updated_at""",
            (int(oid), (data.get("idea") or "").strip(), (data.get("review") or "").strip(),
             int(time.time() * 1000)),
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ---------------------------------------------------------------- CLI（cron 用，无 LLM）

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("sync", "all"):
        print("sync:", json.dumps(sync_fills()))
    if cmd in ("refresh", "all"):
        print("refresh:", json.dumps(refresh_prices()))
