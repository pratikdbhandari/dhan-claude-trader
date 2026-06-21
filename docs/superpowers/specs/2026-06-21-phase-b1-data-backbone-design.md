# Phase B1 — Data Backbone Design

**Date:** 2026-06-21
**Status:** Approved ("do all")
**Depends on:** dhan_client (Phase A stub), accounting engine (consumes leg-dicts)

---

## 1. Purpose

Complete the broker I/O layer and add persistence: finish `dhan_client` (market
data + order lifecycle), add a SQLite `journal` that logs every order with its
signal snapshot and execution result, and bridge journal → accounting via a
`to_legs()` adapter. This is the data backbone every later slice (AI layer, UI,
reports) builds on.

Grounded in the **real installed dhanhq SDK** (inspected): methods `ticker_data`,
`quote_data`, `intraday_minute_data`, `historical_daily_data`, `get_positions`,
`get_holdings`, `place_order` (brackets via `bo_profit_value`/`bo_stop_loss_Value`),
`modify_order`, `cancel_order`. There is **no native exit call**.

---

## 2. dhan_client extensions (`services/dhan_client.py`)

All reads wrapped try/except → raise `DhanError` (surfaced to UI). All order writes
return `OrderResult`; PAPER mode simulates and never contacts the broker.

- `get_ltp(instrument) -> float` — via `ticker_data({segment: [security_id]})`,
  parse last price.
- `get_candles(instrument, interval, lookback_days) -> pd.DataFrame` — OHLCV with
  columns `open,high,low,close,volume`. `interval` ∈ {5, 15, "day"}: 5/15 →
  `intraday_minute_data(..., interval=5|15)`; "day" → `historical_daily_data`.
  Computes `from_date`/`to_date` from `lookback_days`. Normalises SDK response
  (lists per field) into a DataFrame.
- `get_holdings() -> list[dict]`
- `modify_order(order_id, **changes) -> OrderResult`
- `cancel_order(order_id) -> OrderResult`
- `exit_position(instrument) -> OrderResult` — reads net qty from `get_positions`,
  fires opposite-side **MARKET** order to flatten. PAPER simulates. Net-zero → no-op
  `OrderResult(ok=True, status="FLAT")`.
- `place_bracket_order(req) -> OrderResult` — `place_order` with `product_type="BO"`,
  `bo_profit_value=(target-entry)`, `bo_stop_loss_Value=(entry-stop)`. PAPER simulates.

`instrument_type` for historical calls derived from `Instrument.kind`
(INDEX/EQUITY/FUT/OPT → SDK instrument types).

---

## 3. Segment map (`data/segments.py`)

Pure function mapping order context → accounting segment:

```python
def to_segment(product_type: str, kind: str) -> str:
    k = kind.upper()
    if k in ("FUT", "FUTURES"): return "futures"
    if k in ("OPT", "OPTION", "OPTIONS"): return "options"
    # equity
    return "equity_intraday" if product_type.upper() in ("INTRADAY", "INTRA") \
        else "equity_delivery"
```

---

## 4. Journal (`data/journal.py`, SQLite `trades.db`)

### Schema
```sql
CREATE TABLE IF NOT EXISTS trades (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at      TEXT NOT NULL,        -- ISO8601
  mode            TEXT NOT NULL,        -- PAPER | LIVE
  symbol          TEXT NOT NULL,
  security_id     TEXT,
  exchange_segment TEXT,
  product_type    TEXT,                 -- INTRADAY | CNC | BO ...
  kind            TEXT,                 -- EQUITY | INDEX | FUT | OPT
  side            TEXT NOT NULL,        -- BUY | SELL
  order_type      TEXT,                 -- MARKET | LIMIT | BRACKET
  qty             INTEGER NOT NULL,
  -- signal snapshot
  signal          TEXT,
  confidence      INTEGER,
  entry           REAL, stop_loss REAL, target REAL,
  rr_predicted    REAL,
  reasoning       TEXT,
  consensus_json  TEXT,                 -- full ConsensusSignal for audit
  -- execution result
  dhan_order_id   TEXT,
  exec_status     TEXT,                 -- PLACED | REJECTED | FILLED | ERROR | FLAT
  exec_price      REAL,
  error_message   TEXT,
  -- outcome (filled later)
  exit_price      REAL,
  pnl             REAL,
  rr_achieved     REAL,
  closed_at       TEXT
);
```

### API
- `init_db(path) -> sqlite3.Connection` — idempotent (`CREATE TABLE IF NOT EXISTS`).
- `log_order(conn, req: OrderRequest, result: OrderResult, consensus=None) -> int`
  — inserts a row from the order request + result (+ optional consensus snapshot).
  Derives `kind`/`product_type` from the instrument/request. Returns row id.
- `list_trades(conn, mode=None) -> list[dict]` — all rows, optional mode filter,
  newest first.
- `stats(conn, mode) -> dict` — `{trades, wins, win_rate, avg_rr_predicted,
  avg_rr_achieved}` over closed rows (pnl not null).
- `to_legs(conn, mode) -> list[dict]` — accounting leg-dicts from rows where
  `exec_status IN ('FILLED','PLACED')`. Each →
  `{symbol, segment, side, qty, price, mode, timestamp, rr_predicted}` where
  `segment = to_segment(product_type, kind)`, `price = exec_price or entry`,
  `timestamp = created_at`.

---

## 5. Data Flow

```
place order → dhan_client.place_order/place_bracket_order → OrderResult
           → journal.log_order(req, result, consensus)      [ALL orders: audit]
           → journal.to_legs(mode)  [FILLED/PLACED only]     → leg-dicts
           → accounting.realized_trades / portfolio / pnl_statement
candles: dhan_client.get_candles(interval) → strategy engine (Phase A)
ltp:     dhan_client.get_ltp → accounting.portfolio(ltp_fn) unrealized
```

---

## 6. Error / Edge Handling

- Read failures → `DhanError` with clear message (UI surfaces, app does not crash).
- Order failures → `OrderResult(ok=False, status="ERROR", error_message=...)`.
- `exit_position` with flat/zero net → `OrderResult(ok=True, status="FLAT")`.
- Empty candle response → empty DataFrame with correct columns.
- `to_legs` skips non-filled rows; missing `exec_price` falls back to `entry`.
- Journal is local SQLite; path configurable (defaults `trades.db`).

---

## 7. Testing (TDD)

- `dhan_client`: FakeSDK returning dhanhq-shaped dicts.
  - `get_ltp` parses last price.
  - `get_candles` builds DataFrame (5/15/day) with right columns/rows.
  - `exit_position` reads net qty, fires opposite MARKET; PAPER no SDK call; flat → FLAT.
  - `place_bracket_order` passes bo params in LIVE; PAPER simulates.
  - read error → DhanError; write error → OrderResult ok=False.
- `segments`: each (product_type, kind) → expected segment.
- `journal`: temp sqlite — log_order roundtrip; list_trades mode filter; stats win
  rate + avg R:R; to_legs filled-only + segment mapping + price fallback.

---

## 8. Out of Scope (later slices)

AI signal engine, news, fundamentals (B2); risk gate, Streamlit UI, confirm dialog
(B3); EOD report, accounting UI page (B4). No order-status polling/websockets in B1
(fills assumed from order response; reconciliation later if needed).
