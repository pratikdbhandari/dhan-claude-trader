# Phase B1: Data Backbone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish `dhan_client` market-data + order-lifecycle methods, add a SQLite `journal` that logs every order with signal + result, and bridge journal → accounting via `to_legs()`.

**Architecture:** `dhan_client` wraps the real dhanhq SDK (injected for tests). `data/segments.py` is a pure map. `data/journal.py` owns SQLite persistence + queries + the accounting leg adapter. Tests use a FakeSDK with dhanhq-shaped responses and a temp SQLite file — no network.

**Tech Stack:** Python 3.13, dhanhq, pandas, sqlite3 (stdlib), pytest.

> **dhanhq response-shape caveat:** market-data parsers are written defensively
> against the documented shapes; `intraday_minute_data`/`historical_daily_data`
> return dict-of-lists (`open/high/low/close/volume/timestamp`). `ticker_data`'s
> exact nesting is parsed tolerantly (walk for `last_price`/`ltp`); verify against a
> live call before trusting LTP in production. This is noted, not a placeholder.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `data/__init__.py` (create) | package marker |
| `data/segments.py` (create) | `to_segment(product_type, kind)` pure map |
| `services/dhan_client.py` (modify) | get_ltp, get_candles, get_holdings, modify_order, cancel_order, exit_position, place_bracket_order |
| `data/journal.py` (create) | init_db, log_order, list_trades, stats, to_legs |
| `tests/test_segments.py`, `tests/test_dhan_client_data.py`, `tests/test_journal.py` | TDD |

---

## Task 1: Segment map

**Files:** Create `data/__init__.py` (empty), `data/segments.py`; Test `tests/test_segments.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_segments.py
from data.segments import to_segment

def test_equity_intraday_vs_delivery():
    assert to_segment("INTRADAY", "EQUITY") == "equity_intraday"
    assert to_segment("CNC", "EQUITY") == "equity_delivery"

def test_fut_and_opt():
    assert to_segment("INTRADAY", "FUT") == "futures"
    assert to_segment("INTRADAY", "OPT") == "options"
    assert to_segment("NRML", "OPTION") == "options"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_segments.py -v`
Expected: FAIL `ModuleNotFoundError: data.segments`

- [ ] **Step 3: Implement**

```python
# data/__init__.py
# (empty package marker)
```
```python
# data/segments.py
"""Map order context to an accounting segment (matches charges.json keys)."""
from __future__ import annotations


def to_segment(product_type: str, kind: str) -> str:
    k = (kind or "").upper()
    if k in ("FUT", "FUTURES"):
        return "futures"
    if k in ("OPT", "OPTION", "OPTIONS"):
        return "options"
    return "equity_intraday" if (product_type or "").upper() in ("INTRADAY", "INTRA") \
        else "equity_delivery"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_segments.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add data/__init__.py data/segments.py tests/test_segments.py
git commit -m "feat(segments): product_type+kind -> accounting segment map"
```

---

## Task 2: dhan_client.get_ltp

**Files:** Modify `services/dhan_client.py`; Test `tests/test_dhan_client_data.py`.

> `ticker_data(securities)` is called with `{exchange_segment: [int(security_id)]}`.
> Parser walks the response dict for the first `last_price`/`ltp` value.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dhan_client_data.py
import pytest
from services.dhan_client import DhanClient, DhanError
from core.models import Instrument, TradeMode

class DataSDK:
    def ticker_data(self, securities):
        return {"status": "success",
                "data": {"data": {"NSE_EQ": {"2885": {"last_price": 2500.5}}}}}

def _instr():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                      security_id="2885", kind="EQUITY")

def test_get_ltp_parses_last_price():
    c = DhanClient(sdk=DataSDK(), mode=TradeMode.PAPER)
    assert c.get_ltp(_instr()) == 2500.5

def test_get_ltp_error_surfaced():
    class Boom:
        def ticker_data(self, securities): raise RuntimeError("net down")
    c = DhanClient(sdk=Boom(), mode=TradeMode.PAPER)
    with pytest.raises(DhanError):
        c.get_ltp(_instr())
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: FAIL `AttributeError: 'DhanClient' object has no attribute 'get_ltp'`

- [ ] **Step 3: Add to `services/dhan_client.py`** (new methods on `DhanClient`; add `import pandas as pd` and `from datetime import datetime, timedelta` at top)

```python
    def get_ltp(self, instrument) -> float:
        try:
            resp = self.sdk.ticker_data(
                {instrument.exchange_segment: [int(instrument.security_id)]})
            price = _walk_for_price(resp)
            if price is None:
                raise DhanError("LTP not found in ticker response")
            return float(price)
        except DhanError:
            raise
        except Exception as e:                       # noqa: BLE001
            log.exception("get_ltp failed")
            raise DhanError(f"Failed to fetch LTP: {e}") from e
```
Add module-level helper (above the class):
```python
def _walk_for_price(obj):
    """Depth-first search for the first last_price/ltp value in a nested dict/list."""
    if isinstance(obj, dict):
        for key in ("last_price", "ltp", "LTP"):
            if key in obj and isinstance(obj[key], (int, float)):
                return obj[key]
        for v in obj.values():
            found = _walk_for_price(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _walk_for_price(v)
            if found is not None:
                return found
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/dhan_client.py tests/test_dhan_client_data.py
git commit -m "feat(dhan): get_ltp via ticker_data with tolerant parse"
```

---

## Task 3: dhan_client.get_candles

**Files:** Modify `services/dhan_client.py`; Test add to `tests/test_dhan_client_data.py`.

> 5/15-min → `intraday_minute_data(security_id, exchange_segment, instrument_type, from_date, to_date, interval)`. "day" → `historical_daily_data(...)`. Both return dict-of-lists. Output: DataFrame with `open,high,low,close,volume` (+ `timestamp` if present).

- [ ] **Step 1: Write the failing test (append)**

```python
def _candle_payload(n=3):
    return {"status": "success", "data": {
        "open": [100.0+i for i in range(n)], "high": [101.0+i for i in range(n)],
        "low": [99.0+i for i in range(n)], "close": [100.5+i for i in range(n)],
        "volume": [1000+i for i in range(n)], "timestamp": [1700000000+i*60 for i in range(n)]}}

class CandleSDK:
    def __init__(self): self.calls = []
    def intraday_minute_data(self, security_id, exchange_segment, instrument_type,
                             from_date, to_date, interval=1):
        self.calls.append(("intra", interval)); return _candle_payload()
    def historical_daily_data(self, security_id, exchange_segment, instrument_type,
                              from_date, to_date, expiry_code=0):
        self.calls.append(("daily", None)); return _candle_payload()

def test_get_candles_5min_dataframe():
    from core.models import Instrument, TradeMode
    sdk = CandleSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    df = c.get_candles(Instrument(symbol="X", exchange_segment="NSE_EQ",
                                  security_id="1", kind="EQUITY"),
                       interval=5, lookback_days=5)
    assert list(df.columns)[:5] == ["open","high","low","close","volume"]
    assert len(df) == 3
    assert sdk.calls[0] == ("intra", 5)

def test_get_candles_day_uses_daily():
    from core.models import Instrument, TradeMode
    sdk = CandleSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    df = c.get_candles(Instrument(symbol="X", exchange_segment="NSE_EQ",
                                  security_id="1", kind="EQUITY"),
                       interval="day", lookback_days=30)
    assert sdk.calls[0][0] == "daily" and len(df) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: FAIL `AttributeError: ... 'get_candles'`

- [ ] **Step 3: Add method + helpers**

```python
    _INSTRUMENT_TYPE = {"EQUITY": "EQUITY", "INDEX": "INDEX",
                        "FUT": "FUTIDX", "OPT": "OPTIDX"}

    def get_candles(self, instrument, interval, lookback_days: int = 5):
        import pandas as pd
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        itype = self._INSTRUMENT_TYPE.get(instrument.kind.upper(), "EQUITY")
        try:
            if interval == "day":
                resp = self.sdk.historical_daily_data(
                    instrument.security_id, instrument.exchange_segment, itype,
                    from_date, to_date)
            else:
                resp = self.sdk.intraday_minute_data(
                    instrument.security_id, instrument.exchange_segment, itype,
                    from_date, to_date, interval=int(interval))
            return _candles_to_df(resp)
        except Exception as e:                       # noqa: BLE001
            log.exception("get_candles failed")
            raise DhanError(f"Failed to fetch candles: {e}") from e
```
Module-level helper:
```python
def _candles_to_df(resp):
    import pandas as pd
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    cols = ["open", "high", "low", "close", "volume"]
    if not all(k in data for k in cols):
        return pd.DataFrame(columns=cols)
    frame = {k: data[k] for k in cols}
    if "timestamp" in data:
        frame["timestamp"] = data["timestamp"]
    return pd.DataFrame(frame)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/dhan_client.py tests/test_dhan_client_data.py
git commit -m "feat(dhan): get_candles (5/15/day) -> OHLCV DataFrame"
```

---

## Task 4: exit_position + order lifecycle (modify/cancel/holdings/bracket)

**Files:** Modify `services/dhan_client.py`; Test add to `tests/test_dhan_client_data.py`.

> `exit_position` reads net qty from `get_positions` and fires the opposite-side
> MARKET order. PAPER simulates. Flat → `OrderResult(ok=True, status="FLAT")`.
> Positions response row shape: `{"securityId","netQty","exchangeSegment"}`.

- [ ] **Step 1: Write the failing test (append)**

```python
from core.models import OrderResult

class ExitSDK:
    def __init__(self, net): self.net = net; self.placed = []
    def get_positions(self):
        return {"status": "success", "data": [
            {"securityId": "2885", "netQty": self.net, "exchangeSegment": "NSE_EQ"}]}
    def place_order(self, **kw):
        self.placed.append(kw); return {"status": "success", "data": {"orderId": "E1"}}

def _ri():
    from core.models import Instrument
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                      security_id="2885", kind="EQUITY")

def test_exit_long_fires_opposite_sell_live():
    c = DhanClient(sdk=ExitSDK(net=10), mode=TradeMode.LIVE)
    res = c.exit_position(_ri())
    assert res.ok and res.status == "PLACED"
    assert c.sdk.placed[0]["transaction_type"] == "SELL"
    assert c.sdk.placed[0]["quantity"] == 10

def test_exit_flat_is_noop():
    c = DhanClient(sdk=ExitSDK(net=0), mode=TradeMode.LIVE)
    res = c.exit_position(_ri())
    assert res.ok and res.status == "FLAT"
    assert c.sdk.placed == []

def test_exit_paper_does_not_call_sdk():
    sdk = ExitSDK(net=5)
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    res = c.exit_position(_ri())
    assert res.ok and res.mode is TradeMode.PAPER
    assert sdk.placed == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: FAIL `AttributeError: ... 'exit_position'`

- [ ] **Step 3: Add methods**

```python
    def get_holdings(self) -> list:
        try:
            resp = self.sdk.get_holdings()
            return resp.get("data", []) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001
            raise DhanError(f"Failed to fetch holdings: {e}") from e

    def modify_order(self, order_id: str, **changes):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="MODIFIED",
                               dhan_order_id=order_id)
        try:
            self.sdk.modify_order(order_id=order_id, **changes)
            return OrderResult(ok=True, mode=TradeMode.LIVE, status="MODIFIED",
                               dhan_order_id=order_id)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def cancel_order(self, order_id: str):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="CANCELLED",
                               dhan_order_id=order_id)
        try:
            self.sdk.cancel_order(order_id)
            return OrderResult(ok=True, mode=TradeMode.LIVE, status="CANCELLED",
                               dhan_order_id=order_id)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def exit_position(self, instrument):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-EXIT-{instrument.symbol}")
        try:
            positions = self.get_positions()
            net = 0
            for p in positions:
                if str(p.get("securityId")) == str(instrument.security_id):
                    net = int(p.get("netQty", 0))
                    break
            if net == 0:
                return OrderResult(ok=True, mode=TradeMode.LIVE, status="FLAT")
            side = "SELL" if net > 0 else "BUY"
            resp = self.sdk.place_order(
                security_id=instrument.security_id,
                exchange_segment=instrument.exchange_segment,
                transaction_type=side, quantity=abs(net),
                order_type="MARKET", product_type="INTRADAY", price=0)
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid)
        except Exception as e:                       # noqa: BLE001
            log.exception("exit_position failed")
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def place_bracket_order(self, req):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-BO-{req.instrument.symbol}",
                               exec_price=req.price)
        try:
            entry = req.price or 0
            profit = round(abs((req.target or entry) - entry), 2)
            stop = round(abs(entry - (req.stop_loss or entry)), 2)
            resp = self.sdk.place_order(
                security_id=req.instrument.security_id,
                exchange_segment=req.instrument.exchange_segment,
                transaction_type=req.side.value, quantity=req.qty,
                order_type=req.order_type.value, product_type="BO", price=entry,
                bo_profit_value=profit, bo_stop_loss_Value=stop)
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid, exec_price=entry)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dhan_client_data.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add services/dhan_client.py tests/test_dhan_client_data.py
git commit -m "feat(dhan): exit_position + modify/cancel/holdings/bracket order"
```

---

## Task 5: Journal init_db + log_order + list_trades

**Files:** Create `data/journal.py`; Test `tests/test_journal.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_journal.py
import pytest
from data.journal import init_db, log_order, list_trades
from core.models import (Instrument, OrderRequest, OrderResult, Side, OrderType,
                         TradeMode)

@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "trades.db"))

def _req():
    return OrderRequest(instrument=Instrument(symbol="RELIANCE",
                        exchange_segment="NSE_EQ", security_id="2885", kind="EQUITY"),
                        side=Side.BUY, order_type=OrderType.MARKET, qty=10, price=2500.0)

def test_log_and_list_roundtrip(conn):
    res = OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                      dhan_order_id="P1", exec_price=2500.0)
    rid = log_order(conn, _req(), res)
    assert isinstance(rid, int)
    rows = list_trades(conn)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE"
    assert rows[0]["exec_status"] == "PLACED"
    assert rows[0]["mode"] == "PAPER"

def test_list_filters_by_mode(conn):
    log_order(conn, _req(), OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED"))
    log_order(conn, _req(), OrderResult(ok=True, mode=TradeMode.LIVE, status="PLACED"))
    assert len(list_trades(conn, mode="PAPER")) == 1
    assert len(list_trades(conn, mode="LIVE")) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_journal.py -v`
Expected: FAIL `ModuleNotFoundError: data.journal`

- [ ] **Step 3: Implement `data/journal.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_journal.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add data/journal.py tests/test_journal.py
git commit -m "feat(journal): SQLite init_db + log_order + list_trades"
```

---

## Task 6: Journal stats

**Files:** Modify `data/journal.py`; Test add to `tests/test_journal.py`.

> `stats` aggregates rows where `pnl IS NOT NULL` (closed). win = pnl > 0.

- [ ] **Step 1: Write the failing test (append)**

```python
from data.journal import stats

def _close_row(conn, pnl, rr_pred, rr_ach):
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, side, qty,
        pnl, rr_predicted, rr_achieved, exec_status)
        VALUES ('t','PAPER','X','BUY',1,?,?,?,'FILLED')""", (pnl, rr_pred, rr_ach))
    conn.commit()

def test_stats_win_rate_and_avg_rr(conn):
    _close_row(conn, 100, 2.0, 1.8)
    _close_row(conn, -50, 2.0, -1.0)
    s = stats(conn, mode="PAPER")
    assert s["trades"] == 2
    assert s["wins"] == 1
    assert s["win_rate"] == 50.0
    assert s["avg_rr_predicted"] == 2.0
    assert s["avg_rr_achieved"] == pytest.approx(0.4)

def test_stats_empty(conn):
    s = stats(conn, mode="PAPER")
    assert s["trades"] == 0 and s["win_rate"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_journal.py -v`
Expected: FAIL `ImportError: cannot import name 'stats'`

- [ ] **Step 3: Append to `data/journal.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_journal.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add data/journal.py tests/test_journal.py
git commit -m "feat(journal): stats (win rate, avg R:R predicted vs achieved)"
```

---

## Task 7: Journal to_legs (accounting bridge)

**Files:** Modify `data/journal.py`; Test add to `tests/test_journal.py`.

> Legs from rows where `exec_status IN ('FILLED','PLACED')`. `segment = to_segment(
> product_type, kind)`, `price = exec_price or entry`, `timestamp = created_at`.

- [ ] **Step 1: Write the failing test (append)**

```python
from data.journal import to_legs

def test_to_legs_filled_only_with_segment(conn):
    # filled equity intraday buy
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, security_id,
        product_type, kind, side, order_type, qty, entry, exec_price, exec_status)
        VALUES ('2026-06-21T10:00','PAPER','X','1','INTRADAY','EQUITY','BUY','MARKET',
        10, 100, 101, 'PLACED')""")
    # rejected row must be excluded
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, side, qty,
        exec_status) VALUES ('t','PAPER','Y','BUY',5,'REJECTED')""")
    conn.commit()
    legs = to_legs(conn, mode="PAPER")
    assert len(legs) == 1
    leg = legs[0]
    assert leg["symbol"] == "X" and leg["segment"] == "equity_intraday"
    assert leg["price"] == 101 and leg["qty"] == 10 and leg["side"] == "BUY"
    assert leg["mode"] == "PAPER" and leg["timestamp"] == "2026-06-21T10:00"

def test_to_legs_price_falls_back_to_entry(conn):
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, security_id,
        product_type, kind, side, qty, entry, exec_price, exec_status)
        VALUES ('t','PAPER','Z','1','CNC','EQUITY','BUY',1, 200, NULL, 'FILLED')""")
    conn.commit()
    leg = to_legs(conn, mode="PAPER")[0]
    assert leg["price"] == 200 and leg["segment"] == "equity_delivery"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_journal.py -v`
Expected: FAIL `ImportError: cannot import name 'to_legs'`

- [ ] **Step 3: Append to `data/journal.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_journal.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add data/journal.py tests/test_journal.py
git commit -m "feat(journal): to_legs accounting bridge (filled-only)"
```

---

## Task 8: Integration — journal legs feed accounting

**Files:** Test `tests/test_b1_integration.py`.

- [ ] **Step 1: Write the test**

```python
# tests/test_b1_integration.py
"""B1 end-to-end: log orders -> to_legs -> accounting realized P&L."""
import pytest
from data.journal import init_db, log_order, to_legs
from services.accounting import realized_trades
from core.models import (Instrument, OrderRequest, OrderResult, Side, OrderType,
                         TradeMode)

def _req(side, qty, price):
    return OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ",
                        security_id="1", kind="EQUITY"),
                        side=side, order_type=OrderType.MARKET, qty=qty, price=price)

def test_journal_to_accounting_roundtrip(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _req(Side.BUY, 10, 100),
              OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED", exec_price=100))
    log_order(conn, _req(Side.SELL, 10, 110),
              OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED", exec_price=110))
    legs = to_legs(conn, mode="PAPER")
    assert len(legs) == 2
    realized = realized_trades(legs, mode="PAPER")
    assert len(realized) == 1
    assert realized[0].gross_pnl == 100.0
    assert realized[0].net_pnl < 100.0   # charges deducted
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest tests/test_b1_integration.py -v`
Expected: PASS (1 passed) — log_order defaults product_type=INTRADAY, kind=EQUITY → segment equity_intraday → charges applied.

- [ ] **Step 3: Run FULL suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_b1_integration.py
git commit -m "test: B1 integration — journal legs feed accounting P&L"
```

---

## Self-Review Notes (completed)

- **Spec coverage:** §2 dhan_client methods → Tasks 2-4 (get_ltp, get_candles, exit_position, modify/cancel/holdings/bracket). §3 segments → Task 1. §4 journal schema+API → Tasks 5-7 (init/log/list, stats, to_legs). §5 data flow → Task 8 integration. §7 testing → every task TDD with FakeSDK / temp sqlite.
- **Type consistency:** uses existing `Instrument` (has `.kind`), `OrderRequest` (`.price/.stop_loss/.target/.side/.order_type/.qty`), `OrderResult` (`.mode/.status/.dhan_order_id/.exec_price/.error_message`), `TradeMode`. `to_segment(product_type, kind)` signature stable across journal + tests.
- **Placeholder scan:** all code complete. Documented caveat: `ticker_data` response shape parsed tolerantly, flagged for live verification — engineering note, not a TODO.
- **Known assumption:** `log_order` sets `product_type="INTRADAY"` by default (B1 has no per-order product selection yet; B3 UI will pass it). Noted; not a gap for B1's purpose.
- **Execution order:** Task 1 independent. Tasks 2-4 modify dhan_client sequentially (same file). Tasks 5-7 modify journal sequentially. Task 8 depends on all.
