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
  exit_price REAL, pnl REAL, rr_achieved REAL, closed_at TEXT
);
"""


def init_db(path: str = "trades.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def log_order(conn: sqlite3.Connection, req: OrderRequest, result: OrderResult,
              consensus=None) -> int:
    instr = req.instrument
    product_type = "INTRADAY"
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
        "consensus_json": json.dumps(consensus, default=str) if consensus else None,
        "dhan_order_id": result.dhan_order_id, "exec_status": result.status,
        "exec_price": result.exec_price, "error_message": result.error_message,
        "exit_price": None, "pnl": None, "rr_achieved": None, "closed_at": None,
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
