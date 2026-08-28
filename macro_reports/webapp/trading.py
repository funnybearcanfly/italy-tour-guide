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
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template_string, request, session, url_for

HL_API = "https://api.hyperliquid.xyz/info"
DEFAULT_ADDRESS = "0x882b51825750a0D5A0B2cE2CA410Ad27C6ebD4b5"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "trading.db")
# 想法/复盘持久化到 git 跟踪的 JSON，保存时自动 commit+push，避免 DB 丢失
NOTES_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trade_notes.json")

bp = Blueprint("trading", __name__)

_SPOT_NAMES: dict = {}  # spot pair index -> token name，进程内缓存


def _spot_name(coin: str) -> str:
    """把 spot 交易的 '@N' 币种解析成代币名（如 '@107' -> 'FARTCOIN2'）。"""
    if not coin.startswith("@"):
        return coin
    idx = coin  # map key 是 '@107' 全名
    if not _SPOT_NAMES:
        try:
            meta = _hl_post({"type": "spotMeta"})
            tokens = {t["index"]: t["name"] for t in meta.get("tokens", [])}
            for p in meta.get("universe", []):
                toks = p.get("tokens", [])
                if len(toks) == 2:
                    base = tokens.get(toks[0], "?")
                    quote = tokens.get(toks[1], "?")
                    _SPOT_NAMES[str(p["name"])] = f"{base}/{quote}" if base != "USDC" and quote == "USDC" else f"{base}"
        except Exception:
            pass
    return _SPOT_NAMES.get(idx, coin)

_LEV_MAP: dict = {}  # 币种 -> maxLeverage，首次 sync 时加载


def _get_lev_map() -> dict:
    global _LEV_MAP
    if not _LEV_MAP:
        _LEV_MAP = _lev_map()
    return _LEV_MAP


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


HKT = timezone(timedelta(hours=8))


def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=HKT).strftime("%Y-%m-%d %H:%M:%S")


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
  n_liquidations INTEGER NOT NULL DEFAULT 0,
  est_leverage REAL,             -- 名义 / 最低要求保证金（基于 maxLeverage）
  est_margin_used REAL           -- 估算保证金占用（名义 / maxLeverage）
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

CREATE TABLE IF NOT EXISTS hl_flows (
  hash TEXT PRIMARY KEY,
  time INTEGER NOT NULL,
  flow_type TEXT NOT NULL,       -- deposit / withdrawal / transfer_in / transfer_out
  usdc REAL NOT NULL
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
    avg_px = abs(notional / signed) if signed else None
    raw_coin = fills[0]["coin"]
    coin = _spot_name(raw_coin)  # '@107' -> 代币名；perp 原样
    # 杠杆：优先用户实际使用的杠杆（来自持仓 leverage.value），spot 交易无杠杆
    lev = None if raw_coin.startswith("@") else _LEV_MAP.get(raw_coin)
    if lev and notional:
        est_margin = notional / lev
        est_leverage = float(lev)
    else:
        est_margin = notional  # spot 或无杠杆数据：无保证金放大
        est_leverage = 1.0
    conn.execute(
        """INSERT INTO hl_orders (oid, coin, side, opened_at, last_fill_at, n_fills,
               filled_sz, notional_usd, avg_px, closed_pnl, fees, n_liquidations,
               est_leverage, est_margin_used)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(oid) DO UPDATE SET
             coin=excluded.coin, side=excluded.side, opened_at=excluded.opened_at,
             last_fill_at=excluded.last_fill_at, n_fills=excluded.n_fills,
             filled_sz=excluded.filled_sz, notional_usd=excluded.notional_usd,
             avg_px=excluded.avg_px, closed_pnl=excluded.closed_pnl, fees=excluded.fees,
             n_liquidations=excluded.n_liquidations,
             est_leverage=excluded.est_leverage, est_margin_used=excluded.est_margin_used""",
        (
            oid, coin, fills[0]["dir"], fills[0]["time"], fills[-1]["time"],
            len(fills), signed, notional, avg_px,
            closed_pnl, fees, liqs, est_leverage, est_margin,
        ),
    )


def sync_fills(address: str | None = None) -> dict:
    """增量拉取全部历史 fills（自动翻页，API 单次 2000 条封顶），按 tid 去重入库。"""
    address = (address or DEFAULT_ADDRESS).lower()
    conn = _db()
    try:
        _init_db(conn)
        _get_lev_map()
        # 总是从 0 开始翻页：增量成本只有 2 次请求，但从 DB 最小时间起会漏掉更早的历史
        all_fills = []
        cursor = 0
        while True:
            payload = {"type": "userFillsByTime", "user": address, "startTime": cursor}
            batch = _hl_post(payload)
            if not batch:
                break
            all_fills.extend(batch)
            if len(batch) < 2000:
                break
            cursor = max(f["time"] for f in batch) + 1
            time.sleep(0.3)
        new_tids = 0
        touched_oids = set()
        for f in all_fills:
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
            "fetched": len(all_fills),
            "new_fills": new_tids,
            "touched_orders": len(touched_oids),
        }
    finally:
        conn.close()


def refresh_prices(address: str | None = None) -> dict:
    """拉账户状态 + 全市场标记价，更新持仓未实现盈亏与整体杠杆。

    仓位可能分散在主 dex 和任意 HIP-3 builder dex（如 xyz），必须全部遍历。
    """
    address = address or DEFAULT_ADDRESS
    dex_names = [None]  # None = 主 dex
    try:
        for d in _hl_post({"type": "perpDexs"}):
            if d and d.get("name"):
                dex_names.append(d["name"])
    except Exception:
        pass

    positions = []
    total_ntl = 0.0
    margin_used = 0.0
    account_value = 0.0
    for dex in dex_names:
        payload = {"type": "clearinghouseState", "user": address}
        if dex:
            payload["dex"] = dex
        state = _hl_post(payload)
        try:
            meta = _hl_post({"type": "metaAndAssetCtxs"} if not dex
                            else {"type": "metaAndAssetCtxs", "dex": dex})
            universe, ctxs = meta[0]["universe"], meta[1]
            marks = {}
            for name, ctx in zip([u["name"] for u in universe], ctxs):
                if ctx.get("markPx"):
                    marks[name] = float(ctx["markPx"])
        except (KeyError, IndexError, TypeError):
            marks = {}

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
        account_value += float(ms.get("accountValue") or 0)
        total_ntl += float(ms.get("totalNtlPos") or 0)
        margin_used += float(ms.get("totalMarginUsed") or 0)

    # spot 侧权益：只计 available（total - hold），避免与 perp 保证金双记
    spot_equity = 0.0
    try:
        spot_state = _hl_post({"type": "spotClearinghouseState", "user": address})
        spot_meta = _hl_post({"type": "spotMetaAndAssetCtxs"})
        # token index -> 当前价（pair 以 base token 计价）
        tok_idx_name = {t["index"]: t["name"] for t in spot_meta[0]["tokens"]}
        tok_prices = {}
        for pr, ctx in zip(spot_meta[0]["universe"], spot_meta[1]):
            base, quote = pr["tokens"]
            px = ctx.get("markPx")
            if px:
                tok_prices[tok_idx_name.get(base)] = float(px)
                if pr.get("name") == "PURR/USDC":
                    tok_prices["PURR"] = float(px)
        for b in spot_state.get("balances", []):
            name = b["coin"]
            avail = float(b.get("total") or 0) - float(b.get("hold") or 0)
            if name == "USDC":
                spot_equity += avail
            elif name in tok_prices:
                spot_equity += avail * tok_prices[name]
    except Exception:
        spot_equity = None
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
                json.dumps({"positions": positions, "spot_equity": spot_equity}, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "account_value": account_value,
        "spot_equity": spot_equity,
        "total_equity": account_value + (spot_equity or 0),
        "unrealized_pnl": unreal,
        "leverage": (total_ntl / account_value) if account_value else None,
        "n_positions": len(positions),
        "fetched_at": int(time.time() * 1000),
    }


def _lev_map() -> dict:
    """各币种实际使用的杠杆。

    数据源优先级：clearinghouseState 持仓里的 leverage.value（用户真实选择的杠杆，
    isolated/cross 均适用）> meta.maxLeverage（该币允许的上限，fallback）。
    覆盖主 dex + 全部 HIP-3 dex，1 小时过期。
    """
    cache = os.path.join(DATA_DIR, "hl_lev_cache.json")
    try:
        with open(cache) as f:
            blob = json.load(f)
        if time.time() - blob.get("fetched_at", 0) < 3600:
            return blob.get("map", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    lev = {}
    try:
        address = DEFAULT_ADDRESS.lower()
        dexes = [None] + [d["name"] for d in _hl_post({"type": "perpDexs"}) if d and d.get("name")]
        for dex in dexes:
            req = {"type": "clearinghouseState", "user": address}
            if dex:
                req["dex"] = dex
            for ap in _hl_post(req).get("assetPositions", []):
                pos = ap.get("position", {})
                lv = (pos.get("leverage") or {}).get("value")
                if lv:
                    lev[pos["coin"]] = lv
            mreq = {"type": "meta"} if not dex else {"type": "meta", "dex": dex}
            for u in _hl_post(mreq).get("universe", []):
                lev.setdefault(u["name"], u.get("maxLeverage"))
    except Exception:
        if not lev:
            return {}
    try:
        with open(cache, "w") as f:
            json.dump({"fetched_at": time.time(), "map": lev}, f)
    except OSError:
        pass
    return lev


def sync_flows(address: str | None = None) -> dict:
    """同步链上资金流（userNonFundingLedgerUpdates）。

    只计真正进出地址的钱：
      deposit             链上充值入 perp
      accountClassTransfer toPerp=True 算入金，False 算提走（spot 侧）
      send                destination==自己 → perp↔spot 内部划转：
                          destinationDex='spot' = perp→spot（对 perp 是流出），
                          否则 spot→perp（对 perp 是流入）
    """
    address = (address or DEFAULT_ADDRESS).lower()
    updates = _hl_post({"type": "userNonFundingLedgerUpdates", "user": address})
    conn = _db()
    try:
        _init_db(conn)
        n_new = 0
        for u in updates:
            d = u.get("delta", {})
            t = d.get("type")
            flow_type, usdc = None, None
            if t == "deposit":
                flow_type, usdc = "deposit", float(d.get("usdc") or 0)
            elif t == "withdraw":
                flow_type, usdc = "withdrawal", float(d.get("usdc") or 0)
            elif t == "spotTransfer":
                to_self = str(d.get("destination", "")).lower() == address
                from_self = str(d.get("user", "")).lower() == address
                if to_self and not from_self:
                    # 他人转入（USDC/代币/空投）：按转入时 usdcValue 计外部入金
                    flow_type, usdc = "external_transfer_in", float(d.get("usdcValue") or 0)
                elif to_self and from_self:
                    pass  # 自己的划转，不计
                elif from_self:
                    # 转给其他地址 = 资金流出
                    flow_type, usdc = "transfer_out", float(d.get("usdcValue") or 0)
            elif t == "send" and str(d.get("user", "")).lower() == address:
                dest_self = str(d.get("destination", "")).lower() == address
                if dest_self:
                    flow_type = "transfer_out" if d.get("destinationDex") == "spot" else "transfer_in"
                    usdc = float(d.get("usdcValue") or d.get("usdc") or 0)
            if flow_type is None or usdc is None:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO hl_flows (hash, time, flow_type, usdc) VALUES (?,?,?,?)",
                (u["hash"], u["time"], flow_type, usdc),
            )
            n_new += cur.rowcount
        conn.commit()
        row = conn.execute(
            """SELECT
                 SUM(CASE WHEN flow_type IN ('deposit','transfer_in','external_transfer_in') THEN usdc ELSE 0 END) inflow,
                 SUM(CASE WHEN flow_type IN ('withdrawal','transfer_out') THEN usdc ELSE 0 END) outflow
               FROM hl_flows"""
        ).fetchone()
        return {
            "ok": True,
            "new": n_new,
            "total_inflow": row["inflow"] or 0.0,
            "total_outflow": row["outflow"] or 0.0,
            "net_inflow": (row["inflow"] or 0.0) - (row["outflow"] or 0.0),
        }
    finally:
        conn.close()


def _fmt_money(v, signed=False) -> str:
    """1234.5 -> '1,234.50'（signed=True 时带 +/-）。"""
    if v is None:
        return "—"
    sign = "+" if (signed and v > 0) else ("-" if v < 0 else "")
    return f"{sign}{abs(v):,.2f}"

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
    flow_row = conn.execute(
        """SELECT
             SUM(CASE WHEN flow_type IN ('deposit','transfer_in','external_transfer_in') THEN usdc ELSE 0 END) inflow,
             SUM(CASE WHEN flow_type IN ('withdrawal','transfer_out') THEN usdc ELSE 0 END) outflow
           FROM hl_flows"""
    ).fetchone()
    stats = dict(agg) if agg else {}
    stats["n_notes"] = n_notes
    stats["net_inflow"] = (flow_row["inflow"] or 0.0) - (flow_row["outflow"] or 0.0)
    stats["gross_inflow"] = flow_row["inflow"] or 0.0
    stats["gross_outflow"] = flow_row["outflow"] or 0.0
    account = None
    if acc:
        pos_blob = json.loads(acc["positions"] or "{}")
        spot_equity = pos_blob.get("spot_equity")
        unreal_pnl = acc["unrealized_pnl"] or 0.0
        total_equity = (acc["account_value"] or 0.0) + (spot_equity or 0.0)
        account = {
            "fetched_at": acc["fetched_at"],
            "account_value": acc["account_value"],
            "spot_equity": spot_equity,
            "total_equity": total_equity,
            "unrealized_pnl": unreal_pnl,
            "leverage": acc["leverage"],
            "margin_used": acc["margin_used"],
            "positions": pos_blob.get("positions", []),
        }
        # 全账户口径：总盈亏 = 总权益 - 累计净入金（涵盖 perp 已/未实现 + spot 侧）
        stats["total_pnl"] = total_equity - stats["net_inflow"]
        stats["total_pnl_scope"] = "equity"
    else:
        stats["total_pnl"] = (stats.get("total_closed_pnl") or 0.0)
        stats["total_pnl_scope"] = "perp_only"
    stats["roi_on_inflow"] = (
        stats["total_pnl"] / stats["net_inflow"] if stats.get("net_inflow") else None
    )
    stats["winrate"] = (
        stats["wins"] / (stats["wins"] + stats["losses"])
        if stats.get("wins") and (stats["wins"] + stats["losses"]) else None
    )
    if account:
        stats["account"] = account
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
  .long { color:#3fb950; font-weight:600; }
  .short { color:#f85149; font-weight:600; }
  .badge { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11px; }
  .b-open { background:#1f6feb33; color:#58a6ff; }
  .b-close { background:#8b949e33; color:#8b949e; }
  .b-liq { background:#f8514933; color:#f85149; }
  .b-has-note { background:#23863633; color:#3fb950; }
  #overlay { position:fixed; inset:0; background:rgba(0,0,0,0.6); display:none; z-index:100; }
  #detail { position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
            background:#161b22; border:1px solid #30363d; border-radius:10px;
            padding:16px; width:min(760px, 94vw); max-height:88vh; overflow-y:auto;
            display:none; z-index:101; box-shadow:0 8px 30px rgba(0,0,0,0.5); }
  #detail .close-x { float:right; cursor:pointer; color:#8b949e; font-size:18px; line-height:1; padding:2px 6px; }
  #detail .close-x:hover { color:#e6edf3; }
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
  <div class="card"><div class="k">总权益（perp+spot）</div><div class="v">${{ _money(stats.account.total_equity) }}</div></div>
  <div class="card"><div class="k">累计入金（净）</div><div class="v">${{ _money(stats.net_inflow) }}</div>
    <div class="k">流入 ${{ _money(stats.gross_inflow) }} / 流出 ${{ _money(stats.gross_outflow) }}</div></div>
  <div class="card"><div class="k">总盈亏（权益−入金，全账户）</div>
    <div class="v {{ 'pos' if stats.total_pnl >= 0 else 'neg' }}">{{ _money(stats.total_pnl, signed=True) }}</div></div>
  <div class="card"><div class="k">总盈亏 / 累计入金</div>
    <div class="v {{ 'pos' if stats.total_pnl >= 0 else 'neg' }}">{{ "%.1f%%"|format(stats.roi_on_inflow*100) if stats.roi_on_inflow is not none else "—" }}</div></div>
  <div class="card"><div class="k">perp 净值</div><div class="v">${{ _money(stats.account.account_value) }}</div>
    {% if stats.account.spot_equity %}<div class="k">spot 闲钱 ${{ _money(stats.account.spot_equity) }}</div>{% endif %}</div>
  <div class="card"><div class="k">未实现盈亏</div>
    <div class="v {{ 'pos' if stats.account.unrealized_pnl >= 0 else 'neg' }}">{{ _money(stats.account.unrealized_pnl, signed=True) }}</div></div>
  <div class="card"><div class="k">整体杠杆</div><div class="v">{{ "%.1fx"|format(stats.account.leverage) if stats.account.leverage else "—" }}</div></div>
  <div class="card"><div class="k">占用保证金</div><div class="v">${{ _money(stats.account.margin_used) }}</div></div>
  <div class="card"><div class="k">已实现盈亏（全部 order）</div>
    <div class="v {{ 'pos' if stats.total_closed_pnl >= 0 else 'neg' }}">{{ _money(stats.total_closed_pnl, signed=True) }}</div></div>
  <div class="card"><div class="k">Order 数 / 胜率</div><div class="v">{{ stats.n_orders }} / {{ "%.0f%%"|format(stats.winrate*100) if stats.winrate is not none else "—" }}</div></div>
  <div class="card"><div class="k">手续费合计</div><div class="v">${{ _money(stats.total_fees) }}</div></div>
  <div class="card"><div class="k">已录入想法</div><div class="v">{{ stats.n_notes }} 个 order</div></div>
</div>
<div class="sub">快照时间：{{ ts_hkt }} (HKT) · 点击行展开 fills 与想法录入</div>

<h2>当前持仓（按头寸大小）</h2>
<div class="tbl-wrap"><table class="posdet">
<tr><th class="l">币种</th><th>方向</th><th>数量</th><th>开仓均价</th><th>标记价</th>
<th>头寸大小</th><th>保证金</th><th>未实现盈亏</th><th>ROI</th><th>杠杆</th><th>强平价</th><th>累计资金费</th></tr>
{% for p in stats.account.positions %}
<tr>
  <td class="l">{{ p.coin|replace("xyz:", "") }}</td>
  <td class="{{ 'long' if p.szi > 0 else 'short' }}">{{ "多" if p.szi > 0 else "空" }}</td>
  <td>{{ "%.4g"|format(p.szi) }}</td>
  <td>{{ "%.6g"|format(p.entry_px) }}</td>
  <td>{{ "%.6g"|format(p.mark_px) }}</td>
  <td>${{ _money(p.position_value) }}</td>
  <td>${{ _money(p.margin_used) }}</td>
  <td class="{{ 'pos' if p.unrealized_pnl >= 0 else 'neg' }}">{{ _money(p.unrealized_pnl, signed=True) }}</td>
  <td>{{ "%.2f%%"|format(p.roi*100) }}</td>
  <td>{{ p.leverage.value }}x{{ " (逐仓)" if p.leverage.type=="isolated" else "" }}</td>
  <td>{{ "%.6g"|format(p.liquidation_px|float) if p.liquidation_px else "—" }}</td>
  <td>{{ _money(p.cum_funding, signed=True) }}</td>
</tr>
{% endfor %}
</table></div>
{% endif %}

<h2>Order 历史（{{ stats.n_orders }}）</h2>
<div class="tbl-wrap"><table id="tbl">
<tr><th class="l">时间 (HKT)</th><th class="l">币种</th><th class="l">方向</th><th>fills</th>
<th>净成交量</th><th>均价</th><th>金额（名义）</th><th>杠杆</th><th>保证金成本</th><th>已实现盈亏</th><th>手续费</th><th class="l">标签</th></tr>
{% for o in orders %}
<tr class="order-row" data-oid="{{ o.oid }}">
  <td class="l">{{ o.time_str }}</td>
  <td class="l">{{ o.coin|replace("xyz:", "") }}</td>
  <td class="l {{ o.side_cls }}">{{ o.side_str }}</td>
  <td>{{ o.n_fills }}</td>
  <td>{{ "%.6g"|format(o.filled_sz) }}</td>
  <td>{{ "%.6g"|format(o.avg_px) if o.avg_px else "—" }}</td>
  <td>${{ _money(o.notional_usd) }}</td>
  <td>{{ "%.0fx"|format(o.est_leverage) if o.est_leverage else "—" }}</td>
  <td>${{ _money(o.est_margin_used) }}</td>
  <td class="{{ 'pos' if o.closed_pnl >= 0 else 'neg' }}">{{ _money(o.closed_pnl, signed=True) }}</td>
  <td>{{ _money(o.fees) }}</td>
  <td class="l">
    {% if o.n_liquidations %}<span class="badge b-liq">清算</span>{% endif %}
    {% if o.idea %}<span class="badge b-has-note">有想法</span>{% endif %}
    {% if o.review %}<span class="badge b-has-note">有复盘</span>{% endif %}
  </td>
</tr>
{% endfor %}
</table></div>

<div id="overlay" onclick="closeDetail()"></div>
<div id="detail">
  <span class="close-x" onclick="closeDetail()">✕</span>
  <div><b id="d-title"></b> <span id="d-meta" class="muted"></span></div>
  <div class="tbl-wrap"><table class="posdet" id="d-fills" style="margin-top:8px"></table></div>
  <div class="lbl">💡 交易想法（下单当时）</div>
  <textarea id="d-idea"></textarea>
  <div class="lbl">📝 事后复盘</div>
  <textarea id="d-review"></textarea>
  <div style="margin-top:10px">
    <button class="btn primary" onclick="saveNote()">保存</button>
    <button class="btn" onclick="closeDetail()">关闭</button>
    <span id="d-msg" class="muted"></span>
  </div>
</div>

<script>
const oidFills = {{ oid_fills_json | safe }};
let curOid = null;

async function postJson(url){
  try {
    const r = await fetch(url, {method:'POST'});
    const t = await r.text();
    try { return JSON.parse(t); }
    catch(e){
      if (r.status === 401) { location.href = '/login'; return {error:'请先登录'}; }
      return {error: `HTTP ${r.status} — 服务可能正在重启，请稍候重试`};
    }
  } catch(e) { return {error: '网络错误 — 服务可能正在重启，请稍候重试'}; }
}
async function doSync(){
  const m = document.getElementById('msg'); m.textContent = '同步中…';
  const r = await postJson('{{ url_for("trading.sync") }}');
  m.textContent = r.ok ? `新增 ${r.new_fills} 笔成交 / ${r.touched_orders} 个 order` : ('失败: '+r.error);
  if(r.ok) setTimeout(()=>location.reload(), 800);
}
async function doRefresh(){
  const m = document.getElementById('msg'); m.textContent = '刷新价格中…';
  const r = await postJson('{{ url_for("trading.refresh") }}');
  m.textContent = r.ok ? `净值 $${r.account_value.toFixed(2)} · 未实现 ${r.unrealized_pnl.toFixed(2)} · ${r.n_positions} 个持仓` : ('失败: '+r.error);
  if(r.ok) setTimeout(()=>location.reload(), 800);
}
function showDetail(oid){
  curOid = oid;
  const fills = oidFills[oid] || [];
  const first = fills[0] || {};
  document.getElementById('d-title').textContent = `Order ${oid} — ${(first.coin||'').replace('xyz:','')}`;
  document.getElementById('d-meta').textContent = `${fills.length} 笔成交`;
  let h = '<tr><th class="l">时间 (HKT)</th><th>价格</th><th>数量</th><th class="l">方向</th><th>金额</th><th>已实现盈亏</th><th>手续费</th></tr>';
  let totAmt = 0;
  for(const f of fills){
    const amt = (f.px*f.sz).toLocaleString('en-US',{minimumFractionDigits:2, maximumFractionDigits:2});
    totAmt += f.px*f.sz;
    h += `<tr><td class="l">${f.time_str}</td><td>${f.px.toLocaleString()}</td><td>${f.sz}</td><td class="l">${f.dir}${f.liq?' <span style="color:#f85149">⚡清算</span>':''}</td><td>$${amt}</td><td>${f.pnl>0?'+':''}${f.pnl.toLocaleString('en-US',{minimumFractionDigits:2, maximumFractionDigits:2})}</td><td>${f.fee.toFixed(4)}</td></tr>`;
  }
  h += `<tr><td class="l" style="color:#8b949e">合计名义</td><td colspan="3"></td><td style="color:#8b949e">$${totAmt.toLocaleString('en-US',{minimumFractionDigits:2, maximumFractionDigits:2})}</td><td colspan="2"></td></tr>`;
  document.getElementById('d-fills').innerHTML = h;
  document.getElementById('d-idea').value = first.idea || '';
  document.getElementById('d-review').value = first.review || '';
  document.getElementById('d-msg').textContent = '';
  document.getElementById('overlay').style.display = 'block';
  document.getElementById('detail').style.display = 'block';
}
function closeDetail(){
  document.getElementById('overlay').style.display = 'none';
  document.getElementById('detail').style.display = 'none';
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
        if stats.get("account") and stats["account"].get("positions"):
            stats["account"]["positions"].sort(key=lambda p: p["position_value"], reverse=True)
        orders = [dict(o) for o in orders]
        for o in orders:
            o["time_str"] = _ts(o["opened_at"])
            o["side_str"] = _fmt_side(o)
            raw = o["side"] or ""
            if raw.startswith("Open Long") or "Short > Long" in raw:
                o["side_cls"] = "long"
            elif raw.startswith("Open Short") or "Long > Short" in raw:
                o["side_cls"] = "short"
            else:
                o["side_cls"] = ""
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
            _money=_fmt_money,
            oid_fills_json=json.dumps(oid_fills, ensure_ascii=False),
            ts_hkt=datetime.fromtimestamp(stats["account"]["fetched_at"] / 1000, tz=HKT).strftime("%Y-%m-%d %H:%M") if stats.get("account") else "",
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


def _export_notes_to_github() -> bool:
    """把 hl_notes 导出到 git 跟踪的 trade_notes.json 并 commit+push（失败不影响保存）。"""
    try:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT oid, idea, review, updated_at FROM hl_notes WHERE idea != '' OR review != ''"
            ).fetchall()
        finally:
            conn.close()
        blob = {
            str(r["oid"]): {"idea": r["idea"], "review": r["review"], "updated_at": r["updated_at"]}
            for r in rows
        }
        with open(NOTES_JSON, "w") as f:
            json.dump(blob, f, ensure_ascii=False, indent=2)
        repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(NOTES_JSON)))
        subprocess.run(["git", "add", os.path.relpath(NOTES_JSON, repo_dir)],
                       cwd=repo_dir, timeout=10, capture_output=True)
        r1 = subprocess.run(["git", "commit", "-m", "notes: trade ideas/reviews update"],
                            cwd=repo_dir, timeout=15, capture_output=True)
        if r1.returncode == 0:
            subprocess.run(["git", "push", "-q"], cwd=repo_dir, timeout=30, capture_output=True)
        return True
    except Exception:
        return False


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
    finally:
        conn.close()
    ok_git = _export_notes_to_github()
    return jsonify({"ok": True, "synced_to_github": ok_git})


# ---------------------------------------------------------------- CLI（cron 用，无 LLM）

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("sync", "all"):
        print("sync:", json.dumps(sync_fills()))
    if cmd in ("flows", "all"):
        print("flows:", json.dumps(sync_flows()))
    if cmd in ("refresh", "all"):
        print("refresh:", json.dumps(refresh_prices()))
