"""SQLite trade journal. Logs every order with signal snapshot + execution result;
provides queries and an accounting leg adapter."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from core.models import OrderRequest, OrderResult
from data.segments import to_segment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL, mode TEXT NOT NULL, symbol TEXT NOT NULL,
  security_id TEXT, exchange_segment TEXT, product_type TEXT, kind TEXT,
  side TEXT NOT NULL, order_type TEXT, qty INTEGER NOT NULL,
  signal TEXT, confidence INTEGER, entry REAL, stop_loss REAL, target REAL,
  rr_predicted REAL, reasoning TEXT, consensus_json TEXT,
  dhan_order_id TEXT, exec_status TEXT, exec_price REAL, error_message TEXT,
  exit_price REAL, pnl REAL, rr_achieved REAL, closed_at TEXT,
  strategy_tag TEXT, planned_exit_date TEXT, plan_target REAL, plan_stop REAL
);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Additive migration for existing DBs — add BTST columns if missing."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(trades)")}
    for col, decl in (("strategy_tag", "TEXT"), ("planned_exit_date", "TEXT"),
                      ("plan_target", "REAL"), ("plan_stop", "REAL")):
        if col not in have:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")


def init_db(path: str = "trades.db") -> sqlite3.Connection:
    # check_same_thread=False: the connection is cached once (@st.cache_resource)
    # and reused across Streamlit's per-rerun worker threads. Safe here — this is
    # a single-user app and SQLite serialises its own access.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn


def _consensus_to_json(consensus) -> str | None:
    """Serialize a ConsensusSignal into a JSON dict (so the EOD leaderboard can read
    per-provider calls). Returns None if no consensus."""
    if consensus is None:
        return None
    providers = [{"provider": p.provider, "signal": p.signal.value,
                  "confidence": p.confidence}
                 for p in getattr(consensus, "providers", [])]
    return json.dumps({
        "consensus": getattr(getattr(consensus, "consensus", None), "value", None),
        "avg_confidence": getattr(consensus, "avg_confidence", None),
        "agreement_pct": getattr(consensus, "agreement_pct", None),
        "providers": providers,
    })


def log_order(conn: sqlite3.Connection, req: OrderRequest, result: OrderResult,
              consensus=None, *, strategy_tag=None, planned_exit_date=None,
              plan_target=None, plan_stop=None) -> int:
    instr = req.instrument
    # Reflect the real product so accounting/charges segment correctly
    # (to_segment maps non-INTRADAY -> equity_delivery, e.g. BTST CNC).
    product_type = getattr(req, "product_type", "INTRADAY") or "INTRADAY"
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": result.mode.value, "symbol": instr.symbol,
        "security_id": instr.security_id, "exchange_segment": instr.exchange_segment,
        "product_type": product_type, "kind": instr.kind,
        "side": req.side.value, "order_type": req.order_type.value, "qty": req.qty,
        "signal": getattr(getattr(consensus, "consensus", None), "value", None),
        "confidence": getattr(consensus, "avg_confidence", None),
        "entry": req.price, "stop_loss": req.stop_loss, "target": req.target,
        "rr_predicted": None, "reasoning": None,
        "consensus_json": _consensus_to_json(consensus),
        "dhan_order_id": result.dhan_order_id, "exec_status": result.status,
        "exec_price": result.exec_price, "error_message": result.error_message,
        "exit_price": None, "pnl": None, "rr_achieved": None, "closed_at": None,
        "strategy_tag": strategy_tag, "planned_exit_date": planned_exit_date,
        "plan_target": plan_target, "plan_stop": plan_stop,
    }
    cols = ", ".join(row.keys())
    qs = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO trades ({cols}) VALUES ({qs})", list(row.values()))
    conn.commit()
    return cur.lastrowid


def list_trades(conn: sqlite3.Connection, mode: str | None = None) -> list[dict]:
    if mode:
        rows = conn.execute("SELECT * FROM trades WHERE mode=? ORDER BY id DESC",
                            (mode,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def stats(conn: sqlite3.Connection, mode: str) -> dict:
    rows = conn.execute(
        "SELECT pnl, rr_predicted, rr_achieved FROM trades "
        "WHERE mode=? AND pnl IS NOT NULL", (mode,)).fetchall()
    n = len(rows)
    if n == 0:
        return {"trades": 0, "wins": 0, "win_rate": 0.0,
                "avg_rr_predicted": 0.0, "avg_rr_achieved": 0.0}
    wins = sum(1 for r in rows if r["pnl"] > 0)
    rp = [r["rr_predicted"] for r in rows if r["rr_predicted"] is not None]
    ra = [r["rr_achieved"] for r in rows if r["rr_achieved"] is not None]
    return {
        "trades": n, "wins": wins, "win_rate": round(wins / n * 100, 2),
        "avg_rr_predicted": round(sum(rp) / len(rp), 2) if rp else 0.0,
        "avg_rr_achieved": round(sum(ra) / len(ra), 2) if ra else 0.0,
    }


def to_legs(conn: sqlite3.Connection, mode: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM trades WHERE mode=? AND exec_status IN ('FILLED','PLACED') "
        "ORDER BY id ASC", (mode,)).fetchall()
    legs = []
    for r in rows:
        price = r["exec_price"] if r["exec_price"] is not None else r["entry"]
        if price is None or r["qty"] is None or r["qty"] <= 0:
            continue
        legs.append({
            "symbol": r["symbol"],
            "segment": to_segment(r["product_type"], r["kind"]),
            "side": r["side"], "qty": r["qty"], "price": price,
            "mode": r["mode"], "timestamp": r["created_at"],
            "rr_predicted": r["rr_predicted"],
        })
    return legs


def open_btst_book(conn: sqlite3.Connection, mode: str) -> list[dict]:
    """Open overnight BTST positions: BTST buys with no matching BTST sell of the
    same symbol. Net qty per symbol = buys - sells; a symbol is open if net > 0."""
    rows = conn.execute(
        "SELECT * FROM trades WHERE mode=? AND strategy_tag='BTST' "
        "AND exec_status IN ('FILLED','PLACED') ORDER BY id ASC", (mode,)).fetchall()
    net: dict[str, int] = {}
    latest_buy: dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        signed = r["qty"] if r["side"] == "BUY" else -r["qty"]
        net[sym] = net.get(sym, 0) + signed
        if r["side"] == "BUY":
            latest_buy[sym] = dict(r)
    book = []
    for sym, qty in net.items():
        if qty > 0 and sym in latest_buy:
            b = latest_buy[sym]
            book.append({
                "symbol": sym, "qty": qty, "entry": b["exec_price"] or b["entry"],
                "plan_target": b["plan_target"], "plan_stop": b["plan_stop"],
                "planned_exit_date": b["planned_exit_date"],
                "security_id": b["security_id"],
                "exchange_segment": b["exchange_segment"],
            })
    return book
