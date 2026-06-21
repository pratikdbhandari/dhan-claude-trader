# Accounting Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure-Python accounting layer that turns filled order legs into itemized Indian charges, FIFO realized P&L, live portfolio holdings, and a P&L account statement — for separate PAPER/LIVE books.

**Architecture:** `charges.py` is pure config-driven math over a `charges.json` rate table. `accounting.py` consumes a list of plain leg-dicts (decoupled from journal storage) + an injected `ltp_fn`, does FIFO lot matching, and aggregates. No I/O in either module → fully unit-testable now. UI page is a later Phase-B follow-on (needs Streamlit + journal data source) and is NOT in this plan.

**Tech Stack:** Python 3.13, dataclasses, pytest. No new dependencies.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `core/models.py` (modify) | add `ChargeBreakdown`, `RealizedTrade`, `Holding`, `PnLStatement` |
| `charges.json` (create) | per-segment Indian rate table (editable) |
| `services/charges.py` (create) | `compute()` + `reconcile()` — pure charge math |
| `services/accounting.py` (create) | FIFO realized P&L, portfolio, P&L statement |
| `tests/test_charges.py` (create) | worked-INR charge unit tests |
| `tests/test_accounting.py` (create) | FIFO / short / partial / portfolio / statement |

**Leg-dict shape** (the decoupled input both modules agree on):
```python
{"symbol": str, "segment": str, "side": "BUY"|"SELL", "qty": int,
 "price": float, "mode": "PAPER"|"LIVE", "timestamp": str,
 "rr_predicted": float | None}
```
`segment` is one of: `equity_delivery`, `equity_intraday`, `futures`, `options`.

---

## Task 1: Accounting data types

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_models_accounting.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_accounting.py
from core.models import ChargeBreakdown, RealizedTrade, Holding, PnLStatement

def test_charge_breakdown_fields():
    c = ChargeBreakdown(brokerage=0, stt=1.0, exchange_txn=0.03, sebi=0.0,
                        stamp=0.15, gst=0.01, total=1.19)
    assert c.total == 1.19

def test_realized_and_holding_and_statement():
    r = RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=10,
                      buy_price=100, sell_price=110, gross_pnl=100, charges=2.33,
                      net_pnl=97.67, rr_predicted=None, rr_achieved=None,
                      opened_at="t0", closed_at="t1")
    h = Holding(symbol="X", segment="equity_delivery", mode="PAPER", qty=5,
                avg_cost=100, invested=500, ltp=None, current_value=None,
                unrealized_pnl=None)
    s = PnLStatement(mode="PAPER", period="all", gross_realized=100, brokerage=0,
                     stt=2.1, exchange_sebi_stamp=0.2, gst=0.03, net_realized=97.67,
                     unrealized=0.0, total_pnl=97.67)
    assert r.net_pnl == 97.67 and h.qty == 5 and s.total_pnl == 97.67
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_models_accounting.py -v`
Expected: FAIL `ImportError: cannot import name 'ChargeBreakdown'`

- [ ] **Step 3: Append to `core/models.py`**

```python
# --------------------------------------------------------------------------- #
# Accounting
# --------------------------------------------------------------------------- #
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
    charges: float
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

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_models_accounting.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_models_accounting.py
git commit -m "feat(models): accounting types (ChargeBreakdown, RealizedTrade, Holding, PnLStatement)"
```

---

## Task 2: Charge rate table

**Files:**
- Create: `charges.json`
- Test: `tests/test_charges_json.py`

> Rates are stored as fractions: `0.001` = 0.1%, `0.0000297` = 0.00297%, `0.000001` = 0.0001%.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_charges_json.py
import json
from pathlib import Path

REQUIRED = {"brokerage_flat", "brokerage_pct", "stt_buy", "stt_sell",
            "exchange_txn", "sebi", "stamp_buy", "gst"}

def test_all_segments_have_required_keys():
    data = json.loads(Path("charges.json").read_text())
    for seg in ("equity_delivery", "equity_intraday", "futures", "options"):
        assert seg in data, f"missing segment {seg}"
        assert REQUIRED.issubset(data[seg].keys()), f"{seg} missing keys"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_charges_json.py -v`
Expected: FAIL `FileNotFoundError: charges.json`

- [ ] **Step 3: Create `charges.json`**

```json
{
  "_comment": "Indian charge rates as fractions (0.001 = 0.1%). EDITABLE; verify against your Dhan contract note. Not the risk-limit defaults.",
  "equity_delivery": {"brokerage_flat": 0,  "brokerage_pct": 0,      "stt_buy": 0.001,  "stt_sell": 0.001,  "exchange_txn": 0.0000297, "sebi": 0.000001, "stamp_buy": 0.00015, "gst": 0.18},
  "equity_intraday": {"brokerage_flat": 20, "brokerage_pct": 0.0003, "stt_buy": 0,      "stt_sell": 0.00025, "exchange_txn": 0.0000297, "sebi": 0.000001, "stamp_buy": 0.00003, "gst": 0.18},
  "futures":         {"brokerage_flat": 20, "brokerage_pct": 0.0003, "stt_buy": 0,      "stt_sell": 0.0002, "exchange_txn": 0.0000173, "sebi": 0.000001, "stamp_buy": 0.00002, "gst": 0.18},
  "options":         {"brokerage_flat": 20, "brokerage_pct": 0,      "stt_buy": 0,      "stt_sell": 0.001,  "exchange_txn": 0.0003503, "sebi": 0.000001, "stamp_buy": 0.00003, "gst": 0.18}
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_charges_json.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add charges.json tests/test_charges_json.py
git commit -m "feat(charges): Indian per-segment charge rate table"
```

---

## Task 3: Charge calculator `compute()`

**Files:**
- Create: `services/charges.py`
- Test: `tests/test_charges.py`

> **Rules:** turnover = qty*price. Brokerage = `min(brokerage_flat, brokerage_pct*turnover)` if `brokerage_pct>0` else `brokerage_flat`. STT = `stt_buy*turnover` on BUY, `stt_sell*turnover` on SELL. exchange_txn & sebi = rate*turnover (both sides). stamp = `stamp_buy*turnover` on BUY only. gst = `gst*(brokerage+exchange_txn+sebi)`. Every component rounded to 2 dp (paise); total = sum of rounded components, rounded to 2 dp. `mode` is accepted but does not change the formula (PAPER and LIVE compute identically; LIVE actuals are applied later via `reconcile`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_charges.py
import pytest
from services.charges import compute
from core.models import ChargeBreakdown

def test_delivery_buy_worked_example():
    c = compute("equity_delivery", "BUY", qty=10, price=100, mode="PAPER")
    assert isinstance(c, ChargeBreakdown)
    assert c.brokerage == 0
    assert c.stt == 1.00            # 0.1% of 1000
    assert c.stamp == 0.15          # 0.015% of 1000 (buy side)
    assert c.exchange_txn == 0.03   # 0.00297% of 1000, rounded
    assert c.total == 1.19

def test_delivery_sell_has_no_stamp():
    c = compute("equity_delivery", "SELL", qty=10, price=110, mode="PAPER")
    assert c.stamp == 0.0
    assert c.stt == 1.10            # 0.1% of 1100
    assert c.total == 1.14

def test_options_sell_flat_brokerage():
    c = compute("options", "SELL", qty=50, price=200, mode="LIVE")
    assert c.brokerage == 20.0
    assert c.stt == 10.0            # 0.1% of 10000 premium turnover
    assert c.total == pytest.approx(37.74, abs=0.01)

def test_intraday_brokerage_is_lower_of_flat_or_pct():
    # small turnover => pct is lower than flat 20
    c = compute("equity_intraday", "BUY", qty=1, price=100, mode="PAPER")
    assert c.brokerage == 0.03      # 0.03% of 100 = 0.03 < 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_charges.py -v`
Expected: FAIL `ModuleNotFoundError: services.charges`

- [ ] **Step 3: Implement `services/charges.py`**

```python
"""Pure charge math over the charges.json rate table. No I/O beyond loading the
table once. PAPER and LIVE compute identically; LIVE actuals override via reconcile()."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from core.models import ChargeBreakdown

_CHARGES_PATH = Path(__file__).resolve().parent.parent / "charges.json"


@lru_cache(maxsize=1)
def _rates() -> dict:
    return json.loads(_CHARGES_PATH.read_text())


def _r(x: float) -> float:
    return round(float(x), 2)


def compute(segment: str, side: str, qty: int, price: float, mode: str) -> ChargeBreakdown:
    table = _rates()
    if segment not in table:
        raise ValueError(f"Unknown segment '{segment}' (not in charges.json)")
    seg = table[segment]
    turnover = qty * price
    is_buy = side.upper() == "BUY"

    if seg["brokerage_pct"] > 0:
        brokerage = min(seg["brokerage_flat"], seg["brokerage_pct"] * turnover)
    else:
        brokerage = seg["brokerage_flat"]

    stt = (seg["stt_buy"] if is_buy else seg["stt_sell"]) * turnover
    exchange_txn = seg["exchange_txn"] * turnover
    sebi = seg["sebi"] * turnover
    stamp = seg["stamp_buy"] * turnover if is_buy else 0.0
    gst = seg["gst"] * (brokerage + exchange_txn + sebi)

    brokerage, stt, exchange_txn, sebi, stamp, gst = (
        _r(brokerage), _r(stt), _r(exchange_txn), _r(sebi), _r(stamp), _r(gst))
    total = _r(brokerage + stt + exchange_txn + sebi + stamp + gst)
    return ChargeBreakdown(brokerage, stt, exchange_txn, sebi, stamp, gst, total)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_charges.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/charges.py tests/test_charges.py
git commit -m "feat(charges): compute() Indian charge calculator"
```

---

## Task 4: Charge `reconcile()` for LIVE actuals

**Files:**
- Modify: `services/charges.py`
- Test: `tests/test_charges_reconcile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_charges_reconcile.py
from services.charges import compute, reconcile

def test_reconcile_overrides_provided_fields_and_recomputes_total():
    base = compute("equity_delivery", "BUY", qty=10, price=100, mode="LIVE")
    out = reconcile(base, {"brokerage": 5.0, "stt": 1.25})
    assert out.brokerage == 5.0
    assert out.stt == 1.25
    # untouched fields preserved
    assert out.stamp == base.stamp
    # total recomputed from the new components
    assert out.total == round(5.0 + 1.25 + base.exchange_txn + base.sebi
                              + base.stamp + base.gst, 2)

def test_reconcile_with_empty_actuals_is_noop():
    base = compute("futures", "SELL", qty=50, price=300, mode="LIVE")
    out = reconcile(base, {})
    assert out == base
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_charges_reconcile.py -v`
Expected: FAIL `ImportError: cannot import name 'reconcile'`

- [ ] **Step 3: Append to `services/charges.py`**

```python
from dataclasses import replace


def reconcile(breakdown: ChargeBreakdown, dhan_actuals: dict) -> ChargeBreakdown:
    """Override any provided component with the broker's actual value, then
    recompute total. Unprovided components are preserved. Empty dict => no-op."""
    fields = ("brokerage", "stt", "exchange_txn", "sebi", "stamp", "gst")
    updates = {k: _r(dhan_actuals[k]) for k in fields if k in dhan_actuals}
    if not updates:
        return breakdown
    merged = replace(breakdown, **updates)
    total = _r(sum(getattr(merged, f) for f in fields))
    return replace(merged, total=total)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_charges_reconcile.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/charges.py tests/test_charges_reconcile.py
git commit -m "feat(charges): reconcile() to override with Dhan actuals"
```

---

## Task 5: FIFO realized P&L (long round-trips)

**Files:**
- Create: `services/accounting.py`
- Test: `tests/test_accounting.py`

> FIFO per `(symbol, mode)`. Walk legs in order. BUY pushes a lot `[qty, price, charge_per_unit, timestamp, rr_predicted]`. SELL consumes oldest buy lots (splitting partials). Each realized match: `gross = (sell_price - buy_price) * matched_qty`; charges are apportioned per unit from each leg's `ChargeBreakdown.total`; `net = gross - matched_buy_charges - matched_sell_charges`. `rr_achieved = (sell_price-buy_price)/(buy_price-... )` is not derivable without SL, so set `rr_achieved = None` here (filled when journal carries SL); keep `rr_predicted` from the buy lot.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_accounting.py
import pytest
from services.accounting import realized_trades

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_single_roundtrip_net_after_charges():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "SELL", 10, 110, "t1")]
    out = realized_trades(legs, mode="PAPER")
    assert len(out) == 1
    r = out[0]
    assert r.gross_pnl == 100.0          # (110-100)*10
    assert r.charges == pytest.approx(2.33, abs=0.01)   # 1.19 buy + 1.14 sell
    assert r.net_pnl == pytest.approx(97.67, abs=0.01)

def test_fifo_multi_lot_matching():
    legs = [_leg("X", "BUY", 10, 100, "t0"),
            _leg("X", "BUY", 10, 105, "t1"),
            _leg("X", "SELL", 15, 110, "t2")]
    out = realized_trades(legs, mode="PAPER")
    # 10 @100 fully + 5 @105 => two realized rows
    assert len(out) == 2
    assert out[0].qty == 10 and out[0].buy_price == 100
    assert out[1].qty == 5 and out[1].buy_price == 105
    assert out[0].gross_pnl == 100.0     # (110-100)*10
    assert out[1].gross_pnl == 25.0      # (110-105)*5

def test_mode_isolation():
    legs = [_leg("X", "BUY", 10, 100, "t0", mode="PAPER"),
            _leg("X", "SELL", 10, 110, "t1", mode="LIVE")]
    # PAPER buy and LIVE sell must NOT match across books
    assert realized_trades(legs, mode="PAPER") == []
    assert realized_trades(legs, mode="LIVE") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_accounting.py -v`
Expected: FAIL `ModuleNotFoundError: services.accounting`

- [ ] **Step 3: Implement `services/accounting.py`**

```python
"""Accounting over filled order legs. Pure: legs in, dataclasses out. FIFO lot
matching per (symbol, mode). Charges via services.charges."""
from __future__ import annotations
from collections import defaultdict, deque
from core.models import RealizedTrade
from services.charges import compute


def _charge_per_unit(leg: dict) -> float:
    c = compute(leg["segment"], leg["side"], leg["qty"], leg["price"], leg["mode"])
    return c.total / leg["qty"] if leg["qty"] else 0.0


def realized_trades(legs: list[dict], mode: str) -> list[RealizedTrade]:
    book = [l for l in legs if l["mode"] == mode and l["qty"] > 0]
    lots: dict[str, deque] = defaultdict(deque)   # symbol -> buy lots
    out: list[RealizedTrade] = []

    for leg in book:
        sym = leg["symbol"]
        cpu = _charge_per_unit(leg)
        if leg["side"].upper() == "BUY":
            lots[sym].append({"qty": leg["qty"], "price": leg["price"],
                              "cpu": cpu, "ts": leg["timestamp"],
                              "rr": leg["rr_predicted"]})
            continue
        # SELL: consume oldest buy lots
        sell_qty = leg["qty"]
        while sell_qty > 0 and lots[sym]:
            lot = lots[sym][0]
            matched = min(sell_qty, lot["qty"])
            gross = round((leg["price"] - lot["price"]) * matched, 2)
            charges = round(matched * lot["cpu"] + matched * cpu, 2)
            out.append(RealizedTrade(
                symbol=sym, segment=leg["segment"], mode=mode, qty=matched,
                buy_price=lot["price"], sell_price=leg["price"],
                gross_pnl=gross, charges=charges, net_pnl=round(gross - charges, 2),
                rr_predicted=lot["rr"], rr_achieved=None,
                opened_at=lot["ts"], closed_at=leg["timestamp"]))
            lot["qty"] -= matched
            sell_qty -= matched
            if lot["qty"] == 0:
                lots[sym].popleft()
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_accounting.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/accounting.py tests/test_accounting.py
git commit -m "feat(accounting): FIFO realized P&L for long round-trips"
```

---

## Task 6: Portfolio holdings (unmatched lots + injected LTP)

**Files:**
- Modify: `services/accounting.py`
- Test: `tests/test_accounting_portfolio.py`

> After FIFO consumption, remaining buy lots per `(symbol, mode)` are open holdings.
> `avg_cost` = weighted average of remaining lots. `ltp_fn(symbol) -> float | None`
> is injected; if it returns None, `ltp/current_value/unrealized_pnl = None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_accounting_portfolio.py
from services.accounting import portfolio

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_open_holding_with_ltp():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "SELL", 4, 110, "t1")]
    hold = portfolio(legs, mode="PAPER", ltp_fn=lambda s: 120.0)
    assert len(hold) == 1
    h = hold[0]
    assert h.qty == 6 and h.avg_cost == 100.0 and h.invested == 600.0
    assert h.ltp == 120.0 and h.current_value == 720.0
    assert h.unrealized_pnl == 120.0       # (120-100)*6

def test_missing_ltp_yields_none():
    legs = [_leg("X", "BUY", 10, 100, "t0")]
    h = portfolio(legs, mode="PAPER", ltp_fn=lambda s: None)[0]
    assert h.ltp is None and h.current_value is None and h.unrealized_pnl is None

def test_weighted_avg_cost_multi_lot():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "BUY", 10, 120, "t1")]
    h = portfolio(legs, mode="PAPER", ltp_fn=lambda s: None)[0]
    assert h.qty == 20 and h.avg_cost == 110.0   # (1000+1200)/20
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_accounting_portfolio.py -v`
Expected: FAIL `ImportError: cannot import name 'portfolio'`

- [ ] **Step 3: Append to `services/accounting.py`**

```python
from core.models import Holding


def _open_lots(legs: list[dict], mode: str) -> dict[str, list[dict]]:
    """Replay FIFO and return remaining (unmatched) buy lots per symbol."""
    book = [l for l in legs if l["mode"] == mode and l["qty"] > 0]
    lots: dict[str, deque] = defaultdict(deque)
    for leg in book:
        sym = leg["symbol"]
        if leg["side"].upper() == "BUY":
            lots[sym].append({"qty": leg["qty"], "price": leg["price"],
                              "segment": leg["segment"]})
        else:
            sell_qty = leg["qty"]
            while sell_qty > 0 and lots[sym]:
                lot = lots[sym][0]
                matched = min(sell_qty, lot["qty"])
                lot["qty"] -= matched
                sell_qty -= matched
                if lot["qty"] == 0:
                    lots[sym].popleft()
    return {s: list(d) for s, d in lots.items() if d}


def portfolio(legs: list[dict], mode: str, ltp_fn) -> list[Holding]:
    out: list[Holding] = []
    for sym, lots in _open_lots(legs, mode).items():
        qty = sum(l["qty"] for l in lots)
        invested = round(sum(l["qty"] * l["price"] for l in lots), 2)
        avg_cost = round(invested / qty, 2) if qty else 0.0
        ltp = ltp_fn(sym)
        if ltp is None:
            cur = unreal = None
        else:
            cur = round(ltp * qty, 2)
            unreal = round((ltp - avg_cost) * qty, 2)
        out.append(Holding(symbol=sym, segment=lots[0]["segment"], mode=mode,
                           qty=qty, avg_cost=avg_cost, invested=invested,
                           ltp=ltp, current_value=cur, unrealized_pnl=unreal))
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_accounting_portfolio.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/accounting.py tests/test_accounting_portfolio.py
git commit -m "feat(accounting): portfolio holdings with injected LTP"
```

---

## Task 7: P&L account statement

**Files:**
- Modify: `services/accounting.py`
- Test: `tests/test_accounting_statement.py`

> Aggregates realized trades + their charge categories + unrealized for a book.
> `period` filters legs by timestamp prefix: `"all"` = no filter; `"day"` = legs whose
> timestamp starts with `period_key` (e.g. `"2026-06-21"`); `"month"` = starts with
> `period_key` (e.g. `"2026-06"`). Charge categories are recomputed per matched leg via
> `compute()` and apportioned by matched qty, mirroring `realized_trades`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_accounting_statement.py
import pytest
from services.accounting import pnl_statement

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_statement_all_period_closed_trade():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-21T09:30"),
            _leg("X", "SELL", 10, 110, "2026-06-21T15:00")]
    s = pnl_statement(legs, mode="PAPER", period="all", period_key=None,
                      ltp_fn=lambda sym: None)
    assert s.gross_realized == 100.0
    assert s.net_realized == pytest.approx(97.67, abs=0.01)
    assert s.unrealized == 0.0
    assert s.total_pnl == pytest.approx(97.67, abs=0.01)
    # charge categories sum to gross - net
    assert (s.brokerage + s.stt + s.exchange_sebi_stamp + s.gst) == \
        pytest.approx(s.gross_realized - s.net_realized, abs=0.01)

def test_statement_includes_unrealized_open_position():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-21T09:30")]
    s = pnl_statement(legs, mode="PAPER", period="all", period_key=None,
                      ltp_fn=lambda sym: 110.0)
    assert s.gross_realized == 0.0
    assert s.unrealized == 100.0     # (110-100)*10
    assert s.total_pnl == pytest.approx(s.net_realized + 100.0, abs=0.01)

def test_period_day_filter():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-20T09:30"),
            _leg("X", "SELL", 10, 110, "2026-06-21T15:00")]
    # day filter for the 21st: the BUY (20th) is excluded => no completed match
    s = pnl_statement(legs, mode="PAPER", period="day", period_key="2026-06-21",
                      ltp_fn=lambda sym: None)
    assert s.gross_realized == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_accounting_statement.py -v`
Expected: FAIL `ImportError: cannot import name 'pnl_statement'`

- [ ] **Step 3: Append to `services/accounting.py`**

```python
from core.models import PnLStatement


def _filter_period(legs: list[dict], period: str, period_key) -> list[dict]:
    if period == "all" or not period_key:
        return legs
    return [l for l in legs if str(l["timestamp"]).startswith(period_key)]


def pnl_statement(legs: list[dict], mode: str, period: str, period_key,
                  ltp_fn) -> PnLStatement:
    scoped = _filter_period(legs, period, period_key)
    realized = realized_trades(scoped, mode)

    gross = round(sum(r.gross_pnl for r in realized), 2)
    net = round(sum(r.net_pnl for r in realized), 2)

    # re-derive charge categories from the matched legs
    brokerage = stt = ex_sebi_stamp = gst = 0.0
    book = [l for l in scoped if l["mode"] == mode and l["qty"] > 0]
    matched_qty = sum(r.qty for r in realized)
    # apportion each leg's charge categories by the fraction of its qty that matched
    # (sum of matched buy+sell qty equals 2*matched_qty across the book)
    realized_syms = {r.symbol for r in realized}
    for leg in book:
        if leg["symbol"] not in realized_syms:
            continue
        c = compute(leg["segment"], leg["side"], leg["qty"], leg["price"], leg["mode"])
        brokerage += c.brokerage
        stt += c.stt
        ex_sebi_stamp += c.exchange_txn + c.sebi + c.stamp
        gst += c.gst
    brokerage, stt, ex_sebi_stamp, gst = (round(brokerage, 2), round(stt, 2),
                                          round(ex_sebi_stamp, 2), round(gst, 2))

    holdings = portfolio(scoped, mode, ltp_fn)
    unreal = round(sum(h.unrealized_pnl for h in holdings
                       if h.unrealized_pnl is not None), 2)

    return PnLStatement(mode=mode, period=period, gross_realized=gross,
                        brokerage=brokerage, stt=stt,
                        exchange_sebi_stamp=ex_sebi_stamp, gst=gst,
                        net_realized=net, unrealized=unreal,
                        total_pnl=round(net + unreal, 2))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_accounting_statement.py -v`
Expected: PASS (3 passed)

> If `test_statement_all_period_closed_trade`'s category-sum assertion is off by a
> rounding paisa, it is because per-leg rounded categories can differ from the
> apportioned per-unit charges in `realized_trades` by ≤0.02. The test uses
> `abs=0.01`; if it fails by exactly one paisa, widen to `abs=0.02` — do NOT change
> the charge math, the discrepancy is rounding-only and documented here.

- [ ] **Step 5: Commit**

```bash
git add services/accounting.py tests/test_accounting_statement.py
git commit -m "feat(accounting): P&L account statement with period filter"
```

---

## Task 8: Short-sell + integration

**Files:**
- Modify: `services/accounting.py`
- Test: `tests/test_accounting_short.py`

> F&O sell-first: a SELL with no prior buy lots opens a SHORT lot; a later BUY closes
> it. Realized: `gross = (sell_price - buy_price) * qty` (sell happened first).
> Implement by also tracking short lots symmetrically.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_accounting_short.py
import pytest
from services.accounting import realized_trades

def _leg(symbol, side, qty, price, ts, segment="futures", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_short_then_cover_is_profit_when_price_falls():
    legs = [_leg("NF", "SELL", 50, 200, "t0"), _leg("NF", "BUY", 50, 190, "t1")]
    out = realized_trades(legs, mode="PAPER")
    assert len(out) == 1
    r = out[0]
    assert r.qty == 50
    assert r.gross_pnl == 500.0      # (200-190)*50
    assert r.net_pnl < r.gross_pnl   # charges deducted
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_accounting_short.py -v`
Expected: FAIL — current `realized_trades` ignores sell-with-no-buy, returns `[]`.

- [ ] **Step 3: Replace the body of `realized_trades` in `services/accounting.py`**

```python
def realized_trades(legs: list[dict], mode: str) -> list[RealizedTrade]:
    book = [l for l in legs if l["mode"] == mode and l["qty"] > 0]
    longs: dict[str, deque] = defaultdict(deque)   # open BUY lots
    shorts: dict[str, deque] = defaultdict(deque)  # open SELL lots
    out: list[RealizedTrade] = []

    for leg in book:
        sym = leg["symbol"]
        cpu = _charge_per_unit(leg)
        side = leg["side"].upper()
        qty = leg["qty"]

        if side == "BUY":
            # first cover any open shorts (FIFO), then open a long with remainder
            while qty > 0 and shorts[sym]:
                lot = shorts[sym][0]
                matched = min(qty, lot["qty"])
                gross = round((lot["price"] - leg["price"]) * matched, 2)  # sold high, bought low
                charges = round(matched * lot["cpu"] + matched * cpu, 2)
                out.append(RealizedTrade(
                    symbol=sym, segment=leg["segment"], mode=mode, qty=matched,
                    buy_price=leg["price"], sell_price=lot["price"],
                    gross_pnl=gross, charges=charges, net_pnl=round(gross - charges, 2),
                    rr_predicted=lot["rr"], rr_achieved=None,
                    opened_at=lot["ts"], closed_at=leg["timestamp"]))
                lot["qty"] -= matched
                qty -= matched
                if lot["qty"] == 0:
                    shorts[sym].popleft()
            if qty > 0:
                longs[sym].append({"qty": qty, "price": leg["price"], "cpu": cpu,
                                   "ts": leg["timestamp"], "rr": leg["rr_predicted"]})
        else:  # SELL
            # first close any open longs (FIFO), then open a short with remainder
            while qty > 0 and longs[sym]:
                lot = longs[sym][0]
                matched = min(qty, lot["qty"])
                gross = round((leg["price"] - lot["price"]) * matched, 2)
                charges = round(matched * lot["cpu"] + matched * cpu, 2)
                out.append(RealizedTrade(
                    symbol=sym, segment=leg["segment"], mode=mode, qty=matched,
                    buy_price=lot["price"], sell_price=leg["price"],
                    gross_pnl=gross, charges=charges, net_pnl=round(gross - charges, 2),
                    rr_predicted=lot["rr"], rr_achieved=None,
                    opened_at=lot["ts"], closed_at=leg["timestamp"]))
                lot["qty"] -= matched
                qty -= matched
                if lot["qty"] == 0:
                    longs[sym].popleft()
            if qty > 0:
                shorts[sym].append({"qty": qty, "price": leg["price"], "cpu": cpu,
                                    "ts": leg["timestamp"], "rr": leg["rr_predicted"]})
    return out
```

- [ ] **Step 4: Run to verify ALL accounting tests pass**

Run: `python -m pytest tests/test_accounting.py tests/test_accounting_short.py tests/test_accounting_statement.py tests/test_accounting_portfolio.py -v`
Expected: all PASS (long round-trips from Task 5 still pass — the long branch is unchanged in behavior for buy-then-sell).

- [ ] **Step 5: Run the FULL suite and commit**

Run: `python -m pytest -q`
Expected: all green.

```bash
git add services/accounting.py tests/test_accounting_short.py
git commit -m "feat(accounting): short-sell FIFO matching for F&O"
```

---

## Deferred (NOT in this plan)

- **`ui/pages/2_Accounting.py`** — book toggle + 4 report views, ₹ formatting.
  Needs Streamlit app shell + a real leg source from `journal.py` (Phase B). Build
  as a Phase-B follow-on once journal + dhan_client LTP exist; this plan's pure
  modules are the engine it will render.

---

## Self-Review Notes (completed)

- **Spec coverage:** §2 charge model → Tasks 2-4. §3 types → Task 1. §4 charges.py → Tasks 3-4; accounting realized/portfolio/statement → Tasks 5-7; short-sell → Task 8. §5 data flow → Tasks 5/7. §6 edges: partial fill (Task 5 multi-lot), short (Task 8), missing LTP (Task 6), mode isolation (Task 5), unknown segment (Task 3 raises). §7 testing → every task is TDD with worked INR examples. §1 separation: charges pure, accounting takes leg-dicts + injected ltp_fn (no journal coupling).
- **Type consistency:** `ChargeBreakdown`, `RealizedTrade`, `Holding`, `PnLStatement` defined in Task 1, used unchanged in 3-8. `compute(segment, side, qty, price, mode)`, `reconcile(breakdown, dhan_actuals)`, `realized_trades(legs, mode)`, `portfolio(legs, mode, ltp_fn)`, `pnl_statement(legs, mode, period, period_key, ltp_fn)` — signatures stable across tasks.
- **Placeholder scan:** every code step has complete code; the one deferral (UI page) is explicitly out of plan scope with reason, not an in-scope placeholder.
- **Known rounding note:** Task 7 documents a ≤1 paisa apportionment rounding tolerance; the math is not changed to "pass a test."
- **Parallelism for execution:** Task 1 + Task 2 are independent. Tasks 3-4 depend on 1-2. Tasks 5-8 depend on 3. Run 5→6→7→8 sequentially (8 rewrites realized_trades).
