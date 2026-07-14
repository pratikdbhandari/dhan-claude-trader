# BTST Signals Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** existing `signal_engine`, `trade_controller`, `risk_manager`, `dhan_client`, `data/journal`, `services/strategies/engine` (confluence), `services/quality_gate`, `core/readiness`.
**Part of a 4-feature sequence** (BTST → warning bell → UI reface → prioritized improvements). This spec covers BTST only. `services/market_clock.py` introduced here is reused by the warning-bell feature next.

---

## 1. Purpose

Add **Buy-Today-Sell-Tomorrow (BTST)** trading to the app: scan the watchlist near
market close, rank stocks with strong end-of-day momentum likely to follow through
next day, present them as candidates with an entry/target/stop plan and reasoning,
place delivery orders through the existing two-step human confirm, and track the open
overnight book until the planned sell the next day.

**Principles carried over (non-negotiable):**
- No order fires without the existing two-step human confirm (`trade_controller.confirm_and_place`).
- All new business logic in pure, unit-tested functions; pages only render.
- PAPER + mock is the default, free, tested path. LIVE stays locked behind the 5-gate readiness check.

**BTST-specific reality baked in:**
- BTST holds overnight → orders use **delivery (CNC)** product, not intraday MIS.
- Overnight = **gap risk**: no stop protection while the market is shut. This is surfaced
  explicitly on every candidate; it is not hidden.

**Out of scope:** multi-day trailing holds (a BTST position is sold the next day, not
rolled), options BTST, automatic order firing, and the other three features in the
sequence.

---

## 2. New / Changed Modules

```
services/market_clock.py   NEW. IST market-time helpers (pure, injectable `now`):
                             is_near_close(now)  -> bool  (15:00–15:30 IST, Mon–Fri)
                             minutes_to_open(now) -> int | None
                             next_trading_day(d)  -> date  (skips Sat/Sun)
                             is_market_open(now)  -> bool  (09:15–15:30 IST, Mon–Fri)
                           (reused by the warning-bell feature next.)

services/btst.py           NEW. Pure BTST candidate scan:
                             scan(instruments, *, candles_fn, confluence_fn,
                                  active_ids, avg_vol_lookback=20) -> list[BtstCandidate]
                           Applies BTST filters over EOD daily candles + confluence,
                           returns ranked candidates with entry/target/stop + why.

core/models.py             ADD @dataclass BtstCandidate (see §4). No change to existing
                           dataclasses.

services/dhan_client.py    CHANGE: place_order / place_bracket_order gain a
                             product_type: str = "INTRADAY" param (backward-compatible).
                             LIVE path passes it to sdk.place_order instead of the
                             hardcoded "INTRADAY".

services/trade_controller.py  ADD prepare_btst_order(candidate, instrument, *, equity,
                             cfg, day_pnl_value, open_count) -> PendingOrder. Builds a
                             CNC OrderRequest (product carried on the request), runs the
                             same pre_trade_check. confirm_and_place unchanged — still the
                             only path that places.

core/models.py             CHANGE: OrderRequest gains product_type: str = "INTRADAY"
                             (default keeps every existing caller identical).

data/journal.py            CHANGE: schema gains strategy_tag, planned_exit_date,
                             plan_target, plan_stop columns (additive ALTER/CREATE).
                             log_order accepts them (all optional, default None).
                             ADD open_btst_book(conn, mode) -> list[dict].

pages/6_BTST.py            NEW. Thin render: Today's Candidates + BTST Book.
```

No existing behaviour changes: every new function param defaults to today's value.

---

## 3. Market Clock (`services/market_clock.py`)

Pure, `now`-injectable so it is testable without waiting for 3 PM. IST = UTC+5:30
(fixed offset; India has no DST). NSE cash session 09:15–15:30, Mon–Fri.

- `is_near_close(now) -> bool` — True when `now` (IST) is a weekday and time in
  [15:00, 15:30]. This is the BTST scan window.
- `is_market_open(now) -> bool` — weekday and time in [09:15, 15:30].
- `minutes_to_open(now) -> int | None` — whole minutes until the next 09:15 open;
  None if market currently open. (Used by the bell feature next; defined here.)
- `next_trading_day(d) -> date` — next calendar day that is Mon–Fri (skips weekends).
  Public NSE holidays are **not** modeled in this slice (documented limitation — a
  BTST placed the day before a holiday will name the wrong exit date; the user still
  confirms manually, so this misinforms rather than misfires). A holiday calendar is
  a candidate for the later "improvements" feature.

---

## 4. BTST Scan (`services/btst.py`) + model

```python
@dataclass
class BtstCandidate:
    instrument: Instrument
    entry: float            # last close (planned buy near today's close)
    target: float           # next-day target
    stop: float             # next-day stop
    net_score: float        # confluence net_score [-1..1]
    close_strength: float   # (close - low) / (high - low) for the day, 0..1
    volume_ratio: float     # today volume / avg volume
    reasons: list[str]      # rule reasons ("close in top 15% of range", ...)
    gap_risk: str           # human note: overnight gap risk, no stop protection
    ai_reasoning: str = ""  # filled by signal_engine for top N (optional)
```

`scan(instruments, *, candles_fn, confluence_fn, active_ids, avg_vol_lookback=20)`:
for each instrument, fetch daily candles via `candles_fn` (injected: live Dhan or
cache); skip if < `avg_vol_lookback`+1 candles or fetch fails (append nothing).
Build the day's confluence via `confluence_fn`. A stock is a BTST candidate when ALL:

1. **Bullish bias** — confluence `bias is SignalType.BUY` and `net_score > 0`.
2. **Strong close** — `close_strength >= 0.7` (close in top 30% of the day's range).
3. **Volume surge** — `volume_ratio >= 1.2` (today > 1.2× the `avg_vol_lookback` mean).
4. **Positive candle** — `close > open` for the day.

`entry = last close`. `target`/`stop` derived from ATR: `target = entry + 1.5*ATR`,
`stop = entry - 1.0*ATR` (reasoned defaults, tunable later, mirrors the existing
snapshot approach). Rank by `net_score * close_strength` desc. `gap_risk` is always
set to the fixed warning string. `reasons` lists which thresholds were cleared.

Event risk (earnings/expiry) is passed in via the caller's existing `event_flags`
(the dashboard already computes EXPIRY from the date; the quality gate already vetoes
RESULTS) — a candidate whose quality gate vetoes on events is dropped before display,
reusing `quality_gate.apply_gate`, not reinvented here.

AI reasoning: the page calls `signal_engine.generate` for the top N candidates only
(cost control) to fill `ai_reasoning`; mock mode gives deterministic free text.

---

## 5. Order Path (delivery / CNC)

- `OrderRequest.product_type` defaults `"INTRADAY"`; BTST sets `"CNC"`.
- `trade_controller.prepare_btst_order` builds the request with `product_type="CNC"`,
  qty via `risk_manager.position_size(equity, entry, stop, cfg.max_risk_per_trade_pct)`,
  then `pre_trade_check` (unchanged gate: 1%/trade, daily loss, max open positions).
- `confirm_and_place` is unchanged. It already routes to `place_bracket_order` when
  SL+target present, else `place_order`; both now forward `req.product_type` to the SDK.
  For BTST we use a plain CNC `place_order` (no bracket — brackets are intraday MIS on
  Dhan), and the target/stop live in the **plan** (journal + BTST Book), enforced by
  the next-day exit signal rather than a broker bracket. `build_order_request` /
  `prepare_btst_order` therefore set order_type MARKET, leave broker SL/target off,
  and stash target/stop in the journal plan columns.
- `data/segments.to_segment` already maps non-INTRADAY → `equity_delivery`, so charges
  and accounting are correct for CNC with no change there.

---

## 6. Journal + BTST Book

Schema (additive; `CREATE TABLE IF NOT EXISTS` gains the columns, and an idempotent
`ALTER TABLE ADD COLUMN` guard upgrades existing `trades.db` files):
`strategy_tag TEXT, planned_exit_date TEXT, plan_target REAL, plan_stop REAL`.

`log_order(..., strategy_tag=None, planned_exit_date=None, plan_target=None,
plan_stop=None)` — all optional; existing callers unaffected. BTST placement passes
`strategy_tag="BTST"`, `planned_exit_date=next_trading_day(today)`, and the plan
target/stop.

`open_btst_book(conn, mode) -> list[dict]` — rows where `strategy_tag='BTST'`,
`exec_status IN ('FILLED','PLACED')`, and no matching sell has closed them (a BTST buy
with no later BTST sell of the same symbol). Each row carries symbol, qty, entry,
plan_target, plan_stop, planned_exit_date.

---

## 7. UI (`pages/6_BTST.py`, thin)

Two sections:

1. **Today's BTST candidates** — if `not is_near_close(now)`: show
   "BTST scan runs 3:00–3:30 PM IST" + a manual "Scan now (preview)" button so the
   user can dry-run any time. Otherwise render candidate cards: symbol, entry/target/
   stop, close-strength + volume-ratio meters, `reasons`, AI reasoning, a red
   **gap-risk** badge, and a "Select →" button → `prepare_btst_order` → the existing
   two-step confirm dialog (delivery). Global risk-block and readiness lock honored
   exactly as the dashboard does.
2. **BTST Book** — `open_btst_book` rows: each open overnight position with its plan
   and `planned_exit_date`. If `next_trading_day` has arrived, show the **SELL
   reminder** and an exit signal state (target hit / stop hit / neither → suggest exit
   near close), with a one-click "Exit" that goes through `dhan_client.exit_position`.

---

## 8. Error / Edge Handling

- Candle fetch failure per instrument → that instrument is skipped, scan continues.
- Off-window access → informative message, manual preview still available.
- Gap risk → always shown; never suppressed.
- LIVE locked behind readiness; PAPER simulated end-to-end (existing behavior).
- `next_trading_day` holiday blind spot → documented; user confirms exit manually.
- DhanError → surfaced in a banner, page still renders.

---

## 9. Testing (TDD, existing pytest style)

- `market_clock`: near-close boundaries (14:59/15:00/15:30/15:31), weekend, open/closed,
  minutes_to_open (before/at/after open, wrap to next day), next_trading_day Fri→Mon.
- `btst.scan`: each of the 4 filters fails a candidate independently; a stock passing
  all 4 appears with correct entry/target/stop and reasons; insufficient candles skipped;
  candles_fn raising is skipped not fatal; ranking order.
- `dhan_client`: place_order/place_bracket_order forward product_type (PAPER assert on
  the simulated result; LIVE via fake sdk asserting the kwarg).
- `trade_controller.prepare_btst_order`: builds CNC request, runs gate, blocks when
  risk fails, never places.
- `journal`: BTST columns round-trip; `open_btst_book` returns only unclosed BTST buys;
  additive migration leaves existing rows intact.
- Pages verified by running, not unit-tested (logic they call is covered).
