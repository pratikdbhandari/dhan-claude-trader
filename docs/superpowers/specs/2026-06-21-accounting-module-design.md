# Accounting Module Design — Dhan-Claude Trader

**Date:** 2026-06-21
**Status:** Approved (pending final user review of this spec)
**Depends on:** journal.py (Phase B raw order log), dhan_client (LTP for unrealized)

---

## 1. Purpose

A small accounting layer that turns raw filled orders into proper books:
itemized charges, FIFO realized P&L, live portfolio holdings, and a P&L account
statement — for both PAPER (dummy) and LIVE trades, kept as separate books.

**Principles:**
- `journal.py` stays a raw order log (unchanged). Accounting is its own layer that
  *reads* journal data.
- `charges.py` is pure math (no I/O), config-driven, testable in isolation.
- `accounting.py` aggregates: depends on journal + charges + an injected LTP function.
- Paper and live books are isolated (mode-partitioned). UI toggles which book to view.
- All currency in INR (₹).

---

## 2. Charge Model

Indian charge rates live in `charges.json` and are **editable** (rates change over
time; the user reconciles against the Dhan contract note). These are NOT the
risk-limit defaults — editing charges needs no approval gate.

| Charge | Equity Delivery | Equity Intraday | Futures | Options |
|---|---|---|---|---|
| Brokerage | ₹0 | ₹20 or 0.03% (lower) | ₹20 or 0.03% (lower) | ₹20 flat / order |
| STT | 0.1% buy+sell | 0.025% sell | 0.02% sell | 0.1% sell (premium) |
| Exchange txn | 0.00297% | 0.00297% | 0.00173% | 0.03503% (premium) |
| SEBI | 0.0001% | 0.0001% | 0.0001% | 0.0001% |
| Stamp duty | 0.015% buy | 0.003% buy | 0.002% buy | 0.003% buy |
| GST | 18% on (brokerage + exchange txn + SEBI) | same | same | same |

> Defaults are current-best, not authoritative. Config-driven so drift is fixable.

**Charge source = hybrid:**
- PAPER trades → formula only.
- LIVE trades → formula default; if Dhan-reported actuals are present, `reconcile()`
  overrides the computed breakdown with actuals.

---

## 3. Data Types (extend `core/models.py`)

```python
@dataclass
class ChargeBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp: float
    gst: float
    total: float

@dataclass
class RealizedTrade:
    symbol: str
    segment: str
    mode: str                 # PAPER | LIVE
    qty: int
    buy_price: float
    sell_price: float
    gross_pnl: float
    charges: float            # buy_charges + sell_charges total
    net_pnl: float
    rr_predicted: Optional[float]
    rr_achieved: Optional[float]
    opened_at: str
    closed_at: str

@dataclass
class Holding:
    symbol: str
    segment: str
    mode: str
    qty: int
    avg_cost: float
    invested: float
    ltp: Optional[float]
    current_value: Optional[float]
    unrealized_pnl: Optional[float]

@dataclass
class PnLStatement:
    mode: str
    period: str               # day | month | all
    gross_realized: float
    brokerage: float
    stt: float
    exchange_sebi_stamp: float
    gst: float
    net_realized: float
    unrealized: float
    total_pnl: float
```

---

## 4. Components

### `charges.py` (pure)
- `compute(segment: str, side: str, qty: int, price: float, mode: str) -> ChargeBreakdown`
  - Reads rate table from `charges.json` (loaded once).
  - Applies per-segment rules; brokerage "lower of flat/percent" where applicable;
    GST on (brokerage + exchange_txn + sebi); side-specific charges (STT/stamp).
- `reconcile(breakdown: ChargeBreakdown, dhan_actuals: dict) -> ChargeBreakdown`
  - Returns a new breakdown overriding any provided actual values.

### `accounting.py`
- `realized_trades(legs, mode) -> list[RealizedTrade]`
  - FIFO lot matching per symbol within a book. Long: match sells to prior buys.
    Short (F&O sell-first): reverse FIFO, match buys to prior sells. Partial fills
    split lots. Charges per leg via `charges.compute`/`reconcile`.
- `portfolio(legs, mode, ltp_fn) -> list[Holding]`
  - Unmatched lots → holdings. `ltp_fn(symbol)->float|None` injected; missing LTP →
    `ltp/current_value/unrealized_pnl = None` ("n/a"); realized still computed.
- `pnl_statement(legs, mode, period, ltp_fn) -> PnLStatement`
  - Aggregates realized + charge categories + unrealized for the period.

**Input `legs`**: filled order legs read from journal `trades` (symbol, segment,
side, qty, price, mode, timestamp, and rr_predicted from the signal).

### `ui/pages/2_Accounting.py`
- Book toggle PAPER/LIVE.
- Four views: Portfolio holdings, Realized P&L, P&L account statement, Charges ledger.
- All ₹-formatted.

---

## 5. Data Flow

```
journal trade leg (side, qty, price, segment, mode, ts, rr_predicted)
  -> charges.compute(...)              [PAPER: formula]
  -> if LIVE & dhan_actuals: reconcile() override
  -> accounting FIFO match (per symbol, per book)
  -> RealizedTrade: gross = (sell-buy)*qty; net = gross - buy_charges - sell_charges
  unmatched buy lots -> Holding (+ injected LTP -> unrealized)
  aggregate by period -> PnLStatement
```

P&L account statement layout:
```
Gross realized P&L            ₹ X
( - ) Brokerage               ₹ ...
( - ) STT                     ₹ ...
( - ) Exchange + SEBI + stamp ₹ ...
( - ) GST                     ₹ ...
= Net realized P&L            ₹ Y
+ Unrealized (open holdings)  ₹ Z
= Total P&L                   ₹ Y+Z
```

---

## 6. Error / Edge Handling

- Partial fills → FIFO splits lots.
- Short sell (sell-first) → reverse FIFO match buys to prior sells.
- Missing LTP → unrealized "n/a"; realized unaffected.
- Zero / negative qty → skip leg.
- Empty book → all reports render zero/empty cleanly.
- Unknown segment in `charges.json` → raise clear error surfaced to UI.

---

## 7. Testing (TDD)

- `charges.py`: unit tests with known INR worked examples per segment (delivery,
  intraday, futures, options), verifying each line + total. Buy-side vs sell-side
  charges. GST base correctness.
- `accounting.py`: synthetic leg sequences — single round-trip (buy 10@100 / sell
  10@110 → known net after charges), multi-lot FIFO, partial fill, short sell,
  missing-LTP portfolio, period aggregation. Paper/live isolation.

---

## 8. Out of Scope

Tax filing/ITR export, multi-currency, dividends/corporate actions, intraday
mark-to-market margining, anything beyond the four reports. Add later only if asked.
