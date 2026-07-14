# BTST Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Buy-Today-Sell-Tomorrow trading: near-close scan of the watchlist for strong end-of-day momentum, ranked candidates with entry/target/stop + reasoning, delivery (CNC) orders through the existing two-step confirm, and an overnight BTST book with a next-day sell reminder.

**Architecture:** New pure modules `market_clock.py` (IST market times) and `btst.py` (candidate scan over daily candles + confluence) feed a thin `pages/6_BTST.py`. Orders reuse `trade_controller`'s two-step confirm with a new CNC product path; the journal gains BTST plan columns and an open-book query. No existing behaviour changes — every new parameter defaults to today's value.

**Tech Stack:** Python 3.13, pandas, Streamlit 1.40.2, pytest — all already in the repo.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-btst-signals-design.md`](../specs/2026-07-14-btst-signals-design.md)

---

## Before You Start

- Branch is `feature/btst-signals` (already created). Do not switch branches.
- Read: `core/models.py` (OrderRequest, Instrument, SignalType, ConfluenceSnapshot), `services/strategies/engine.py` (`build_confluence`), `services/indicators.py` (`atr`), `services/risk_manager.py` (`position_size`, `pre_trade_check`, `RiskConfig`), `services/trade_controller.py` (`PendingOrder`, `build_order_request`, `prepare_order`, `confirm_and_place`), `services/dhan_client.py` (`place_order`, `place_bracket_order`), `data/journal.py` (`init_db`, `log_order`, `to_legs`), `data/segments.py`.
- Test style: pytest, fakes/temp-sqlite (see `tests/test_trade_controller.py`, `tests/conftest.py`). Commit after each task with inline identity: `git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "..."`.
- Run the full suite (`pytest tests/ -q`) at the end of each task; it must stay green.

---

## Task 1: Market Clock

**Files:**
- Create: `services/market_clock.py`
- Test: `tests/test_market_clock.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_market_clock.py`:
```python
from datetime import date, datetime, timezone, timedelta

from services.market_clock import (is_market_open, is_near_close,
                                    minutes_to_open, next_trading_day)

IST = timezone(timedelta(hours=5, minutes=30))


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# 2026-07-14 is a Tuesday; 2026-07-18 Sat, 2026-07-19 Sun, 2026-07-17 Fri.
def test_near_close_true_inside_window():
    assert is_near_close(_ist(2026, 7, 14, 15, 0)) is True
    assert is_near_close(_ist(2026, 7, 14, 15, 30)) is True
    assert is_near_close(_ist(2026, 7, 14, 15, 15)) is True


def test_near_close_false_outside_window():
    assert is_near_close(_ist(2026, 7, 14, 14, 59)) is False
    assert is_near_close(_ist(2026, 7, 14, 15, 31)) is False


def test_near_close_false_on_weekend():
    assert is_near_close(_ist(2026, 7, 18, 15, 15)) is False   # Saturday


def test_market_open_window():
    assert is_market_open(_ist(2026, 7, 14, 9, 15)) is True
    assert is_market_open(_ist(2026, 7, 14, 15, 30)) is True
    assert is_market_open(_ist(2026, 7, 14, 9, 14)) is False
    assert is_market_open(_ist(2026, 7, 14, 15, 31)) is False
    assert is_market_open(_ist(2026, 7, 18, 12, 0)) is False   # Saturday


def test_minutes_to_open_before_open_same_day():
    assert minutes_to_open(_ist(2026, 7, 14, 9, 0)) == 15


def test_minutes_to_open_none_when_open():
    assert minutes_to_open(_ist(2026, 7, 14, 10, 0)) is None


def test_minutes_to_open_after_close_rolls_to_next_day():
    # Tue 16:00 -> next open Wed 09:15 = 17h15m = 1035 min
    assert minutes_to_open(_ist(2026, 7, 14, 16, 0)) == 1035


def test_minutes_to_open_friday_evening_rolls_to_monday():
    # Fri 2026-07-17 18:00 -> Mon 2026-07-20 09:15
    assert minutes_to_open(_ist(2026, 7, 17, 18, 0)) == (2 * 24 * 60) + (15 * 60 + 15)


def test_next_trading_day_skips_weekend():
    assert next_trading_day(date(2026, 7, 17)) == date(2026, 7, 20)   # Fri -> Mon
    assert next_trading_day(date(2026, 7, 14)) == date(2026, 7, 15)   # Tue -> Wed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_clock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.market_clock'`

- [ ] **Step 3: Write `services/market_clock.py`**

```python
"""IST-aware NSE market-time helpers. Pure and `now`-injectable so callers pass a
timezone-aware datetime (tests inject fixed times). IST is a fixed UTC+5:30 offset
(India has no DST). NSE cash session 09:15–15:30, Mon–Fri. Public holidays are NOT
modeled here (documented limitation — next_trading_day only skips weekends)."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

OPEN = time(9, 15)
CLOSE = time(15, 30)
NEAR_CLOSE_START = time(15, 0)


def _ist(now: datetime) -> datetime:
    return now.astimezone(IST)


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5          # Mon=0 .. Fri=4


def is_market_open(now: datetime) -> bool:
    n = _ist(now)
    return _is_weekday(n.date()) and OPEN <= n.time() <= CLOSE


def is_near_close(now: datetime) -> bool:
    n = _ist(now)
    return _is_weekday(n.date()) and NEAR_CLOSE_START <= n.time() <= CLOSE


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while not _is_weekday(nxt):
        nxt += timedelta(days=1)
    return nxt


def minutes_to_open(now: datetime) -> int | None:
    """Whole minutes until the next 09:15 open; None if the market is open now."""
    n = _ist(now)
    if is_market_open(n):
        return None
    # candidate open today, else roll forward to the next weekday's open
    if _is_weekday(n.date()) and n.time() < OPEN:
        target = datetime.combine(n.date(), OPEN, tzinfo=IST)
    else:
        d = next_trading_day(n.date())
        target = datetime.combine(d, OPEN, tzinfo=IST)
    return int((target - n).total_seconds() // 60)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_clock.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add services/market_clock.py tests/test_market_clock.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): IST market clock helpers"
```

---

## Task 2: Model additions (BtstCandidate + OrderRequest.product_type)

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_models_btst.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_models_btst.py`:
```python
from core.models import (BtstCandidate, Instrument, OrderRequest, OrderType,
                         Side)


def test_order_request_defaults_product_type_intraday():
    req = OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ"),
                       side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    assert req.product_type == "INTRADAY"


def test_order_request_accepts_cnc():
    req = OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ"),
                       side=Side.BUY, order_type=OrderType.MARKET, qty=1,
                       product_type="CNC")
    assert req.product_type == "CNC"


def test_btst_candidate_fields():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    c = BtstCandidate(instrument=instr, entry=100.0, target=103.0, stop=98.0,
                      net_score=0.4, close_strength=0.8, volume_ratio=1.5,
                      reasons=["strong close"], gap_risk="overnight gap risk")
    assert c.instrument.symbol == "RELIANCE"
    assert c.ai_reasoning == ""          # default
    assert c.target > c.entry > c.stop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_btst.py -v`
Expected: FAIL — `ImportError: cannot import name 'BtstCandidate'` and product_type AttributeError.

- [ ] **Step 3: Edit `core/models.py`**

Add `product_type` to `OrderRequest` (find the existing dataclass and add the field after `target`):

```python
@dataclass
class OrderRequest:
    instrument: Instrument
    side: Side
    order_type: OrderType
    qty: int
    price: Optional[float] = None        # limit price
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    product_type: str = "INTRADAY"       # "INTRADAY" (MIS) | "CNC" (delivery, BTST)
    # provenance — what signal produced this (for the journal)
    source_signal: Optional[ConsensusSignal] = None
```

Add `BtstCandidate` near the Signals section (after `ConsensusSignal`):

```python
@dataclass
class BtstCandidate:
    """One Buy-Today-Sell-Tomorrow candidate with its next-day plan."""
    instrument: Instrument
    entry: float
    target: float
    stop: float
    net_score: float
    close_strength: float      # (close - low) / (high - low), 0..1
    volume_ratio: float        # today volume / average volume
    reasons: list[str]
    gap_risk: str
    ai_reasoning: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models_btst.py -v`
Expected: 3 passed

- [ ] **Step 5: Confirm no regressions**

Run: `pytest tests/ -q`
Expected: all green (product_type default keeps every existing OrderRequest caller identical).

- [ ] **Step 6: Commit**

```bash
git add core/models.py tests/test_models_btst.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): BtstCandidate model + OrderRequest.product_type"
```

---

## Task 3: BTST Scan

**Files:**
- Create: `services/btst.py`
- Test: `tests/test_btst.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_btst.py`:
```python
import numpy as np
import pandas as pd

from core.models import (ConfluenceSnapshot, Instrument, Regime, SignalType)
from services.btst import scan


def _instr(sym="RELIANCE"):
    return Instrument(symbol=sym, exchange_segment="NSE_EQ", security_id="1")


def _daily(n=40, *, last_close=None, last_high=None, last_low=None,
           last_open=None, vol_last=None, vol_base=1000.0):
    """Build a daily OHLCV frame; the LAST row is the signal day, override-able."""
    rng = np.random.default_rng(0)
    close = np.linspace(90, 100, n)
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.2
    vol = np.full(n, vol_base)
    if last_close is not None: close[-1] = last_close
    if last_high is not None: high[-1] = last_high
    if last_low is not None: low[-1] = last_low
    if last_open is not None: open_[-1] = last_open
    if vol_last is not None: vol[-1] = vol_last
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def _bull_snap(net=0.4):
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[], category_scores={},
                              net_score=net, bias=SignalType.BUY,
                              buy_count=5, sell_count=0, hold_count=0)


def _bear_snap():
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[], category_scores={},
                              net_score=-0.4, bias=SignalType.SELL,
                              buy_count=0, sell_count=5, hold_count=0)


# A day that passes ALL 4 filters: strong close, high volume, green candle, bull bias.
def _passing_df():
    # range 98..104, close 103.4 -> close_strength = (103.4-98)/(104-98)=0.9
    return _daily(last_open=99.0, last_close=103.4, last_high=104.0, last_low=98.0,
                  vol_last=2000.0, vol_base=1000.0)


def test_passing_candidate_appears_with_plan():
    out = scan([_instr()], candles_fn=lambda i: _passing_df(),
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert len(out) == 1
    c = out[0]
    assert c.instrument.symbol == "RELIANCE"
    assert c.entry == 103.4
    assert c.target > c.entry > c.stop            # ATR-derived plan
    assert c.close_strength >= 0.7
    assert c.volume_ratio >= 1.2
    assert c.gap_risk                             # non-empty warning
    assert any("close" in r.lower() for r in c.reasons)


def test_bearish_bias_rejected():
    out = scan([_instr()], candles_fn=lambda i: _passing_df(),
               confluence_fn=lambda df: _bear_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_weak_close_rejected():
    # close near the low of the range -> close_strength < 0.7
    df = _daily(last_open=99.0, last_close=98.6, last_high=104.0, last_low=98.0,
                vol_last=2000.0, vol_base=1000.0)
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_low_volume_rejected():
    df = _daily(last_open=99.0, last_close=103.4, last_high=104.0, last_low=98.0,
                vol_last=1000.0, vol_base=1000.0)     # ratio 1.0 < 1.2
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_red_candle_rejected():
    # close < open
    df = _daily(last_open=104.0, last_close=103.4, last_high=104.5, last_low=98.0,
                vol_last=2000.0, vol_base=1000.0)
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_insufficient_candles_skipped():
    out = scan([_instr()], candles_fn=lambda i: _daily(n=5),
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)),
               avg_vol_lookback=20)
    assert out == []


def test_fetch_error_skipped_not_fatal():
    def boom(i):
        raise RuntimeError("no data")
    out = scan([_instr()], candles_fn=boom,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_ranking_by_score_times_strength():
    a, b = _instr("AAA"), _instr("BBB")
    def cf(df):
        return _bull_snap(net=0.4)
    # both pass; give BBB a stronger close so it ranks first
    def candles(i):
        if i.symbol == "BBB":
            return _daily(last_open=99.0, last_close=103.9, last_high=104.0,
                          last_low=98.0, vol_last=2000.0)
        return _passing_df()
    out = scan([a, b], candles_fn=candles, confluence_fn=cf,
               active_ids=list(range(1, 30)))
    assert [c.instrument.symbol for c in out] == ["BBB", "AAA"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_btst.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.btst'`

- [ ] **Step 3: Write `services/btst.py`**

```python
"""Buy-Today-Sell-Tomorrow candidate scan. Pure: candles + confluence in,
ranked BtstCandidate list out. candles_fn / confluence_fn are injected so the
core is testable offline (live wiring is done by the page)."""
from __future__ import annotations
from core.models import BtstCandidate, SignalType
from services.indicators import atr

CLOSE_STRENGTH_MIN = 0.7
VOLUME_RATIO_MIN = 1.2
TARGET_ATR_MULT = 1.5
STOP_ATR_MULT = 1.0
GAP_RISK_NOTE = ("Overnight gap risk: no stop protection while the market is "
                 "shut; a gap-down can breach the planned stop at the open.")


def _close_strength(row) -> float:
    rng = float(row["high"]) - float(row["low"])
    if rng <= 0:
        return 0.0
    return (float(row["close"]) - float(row["low"])) / rng


def scan(instruments: list, *, candles_fn, confluence_fn, active_ids: list[int],
         avg_vol_lookback: int = 20) -> list[BtstCandidate]:
    out: list[BtstCandidate] = []
    for instr in instruments:
        try:
            df = candles_fn(instr)
        except Exception:                          # noqa: BLE001 - skip, not fatal
            continue
        if df is None or len(df) < avg_vol_lookback + 1:
            continue
        last = df.iloc[-1]
        snap = confluence_fn(df)

        # Filter 1: bullish bias
        if snap.bias is not SignalType.BUY or snap.net_score <= 0:
            continue
        # Filter 2: strong close
        cs = _close_strength(last)
        if cs < CLOSE_STRENGTH_MIN:
            continue
        # Filter 3: volume surge
        avg_vol = float(df["volume"].iloc[-(avg_vol_lookback + 1):-1].mean())
        vol_ratio = float(last["volume"]) / avg_vol if avg_vol > 0 else 0.0
        if vol_ratio < VOLUME_RATIO_MIN:
            continue
        # Filter 4: positive (green) candle
        if float(last["close"]) <= float(last["open"]):
            continue

        entry = float(last["close"])
        a = float(atr(df).dropna().iloc[-1])
        target = round(entry + TARGET_ATR_MULT * a, 2)
        stop = round(entry - STOP_ATR_MULT * a, 2)
        reasons = [
            f"close in top {round((1 - cs) * 100)}% of day range (strength {cs:.2f})",
            f"volume {vol_ratio:.2f}x average",
            "green daily candle",
            f"bullish confluence (net {snap.net_score:.2f})",
        ]
        out.append(BtstCandidate(
            instrument=instr, entry=entry, target=target, stop=stop,
            net_score=snap.net_score, close_strength=round(cs, 2),
            volume_ratio=round(vol_ratio, 2), reasons=reasons,
            gap_risk=GAP_RISK_NOTE))

    out.sort(key=lambda c: c.net_score * c.close_strength, reverse=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_btst.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add services/btst.py tests/test_btst.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): near-close candidate scan with 4 filters + ATR plan"
```

---

## Task 4: dhan_client product_type passthrough

**Files:**
- Modify: `services/dhan_client.py`
- Test: `tests/test_dhan_client_btst.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_dhan_client_btst.py`:
```python
from core.models import Instrument, OrderRequest, OrderType, Side, TradeMode
from services.dhan_client import DhanClient


class FakeSdk:
    def __init__(self):
        self.calls = []

    def place_order(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": {"orderId": "O123"}}


def _req(product_type="CNC"):
    return OrderRequest(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        side=Side.BUY, order_type=OrderType.MARKET, qty=5, price=100.0,
        product_type=product_type)


def test_paper_place_order_reports_product_agnostic_success():
    c = DhanClient(sdk=object(), mode=TradeMode.PAPER)
    res = c.place_order(_req("CNC"))
    assert res.ok and res.status == "PLACED"


def test_live_place_order_forwards_cnc_product_type():
    sdk = FakeSdk()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    c.place_order(_req("CNC"))
    assert sdk.calls[0]["product_type"] == "CNC"


def test_live_place_order_defaults_intraday_when_unset():
    sdk = FakeSdk()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    c.place_order(_req("INTRADAY"))
    assert sdk.calls[0]["product_type"] == "INTRADAY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dhan_client_btst.py -v`
Expected: FAIL — LIVE currently hardcodes `product_type="INTRADAY"`, so the CNC test fails.

- [ ] **Step 3: Edit `services/dhan_client.py`**

In `place_order`, replace the hardcoded product type in the LIVE `sdk.place_order(...)` call:

```python
                product_type=req.product_type,
```
(was `product_type="INTRADAY",`)

In `place_bracket_order`, the LIVE call currently passes `product_type="BO"`. Leave bracket as `"BO"` (brackets are intraday-only on Dhan) — BTST does not use brackets. No change needed there, but add a one-line comment above it:
```python
                # bracket orders are intraday MIS on Dhan; BTST uses plain CNC place_order
                product_type="BO", price=entry,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dhan_client_btst.py -v`
Expected: 3 passed

- [ ] **Step 5: Confirm no regressions**

Run: `pytest tests/test_dhan_client.py tests/test_dhan_client_data.py -q`
Expected: all green (existing callers pass `product_type` defaulting to INTRADAY).

- [ ] **Step 6: Commit**

```bash
git add services/dhan_client.py tests/test_dhan_client_btst.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): forward OrderRequest.product_type to Dhan (CNC delivery)"
```

---

## Task 5: trade_controller.prepare_btst_order

**Files:**
- Modify: `services/trade_controller.py`
- Test: `tests/test_trade_controller_btst.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_trade_controller_btst.py`:
```python
from core.models import Instrument, OrderResult, OrderType, TradeMode, Side
from core.models import BtstCandidate
from services.risk_manager import RiskConfig
from services.trade_controller import prepare_btst_order, confirm_and_place
from data.journal import init_db, list_trades


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        raise AssertionError("BTST must not use bracket orders")


def _cand():
    return BtstCandidate(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        entry=100.0, target=103.0, stop=98.0, net_score=0.4, close_strength=0.9,
        volume_ratio=1.5, reasons=["strong close"], gap_risk="gap risk")


def test_prepare_btst_builds_cnc_request_and_runs_gate():
    pending = prepare_btst_order(_cand(), equity=100000, cfg=RiskConfig(),
                                 day_pnl_value=0, open_count=0)
    req = pending.order_request
    assert req.product_type == "CNC"
    assert req.order_type is OrderType.MARKET
    assert req.side is Side.BUY
    assert req.stop_loss is None and req.target is None    # plan, not broker bracket
    assert req.qty > 0
    assert pending.risk_check.allowed is True


def test_prepare_btst_blocks_when_max_positions_reached():
    pending = prepare_btst_order(_cand(), equity=100000,
                                 cfg=RiskConfig(max_open_positions=2),
                                 day_pnl_value=0, open_count=2)
    assert pending.risk_check.allowed is False


def test_confirm_places_plain_cnc_order_not_bracket(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = prepare_btst_order(_cand(), equity=100000, cfg=RiskConfig(),
                                 day_pnl_value=0, open_count=0)
    res = confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.ok
    assert len(dhan.placed) == 1                      # plain place_order, not bracket
    assert dhan.placed[0].product_type == "CNC"
    assert len(list_trades(conn)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trade_controller_btst.py -v`
Expected: FAIL — `ImportError: cannot import name 'prepare_btst_order'`

- [ ] **Step 3: Edit `services/trade_controller.py`**

Add the import for `BtstCandidate` (extend the existing `core.models` import line) and append:

```python
def prepare_btst_order(candidate, *, equity: float, cfg: RiskConfig,
                       day_pnl_value: float, open_count: int) -> PendingOrder:
    """Build a CNC (delivery) MARKET buy for a BTST candidate and run the same
    pre-trade risk gate. Target/stop live in the plan (journal + BTST book), not a
    broker bracket, so the OrderRequest carries no stop_loss/target — confirm_and_place
    will therefore route to the plain place_order (CNC), never place_bracket_order."""
    qty = risk_manager.position_size(equity, candidate.entry, candidate.stop,
                                     cfg.max_risk_per_trade_pct)
    req = OrderRequest(
        instrument=candidate.instrument, side=Side.BUY, order_type=OrderType.MARKET,
        qty=qty, price=candidate.entry, stop_loss=None, target=None,
        product_type="CNC")
    check = risk_manager.pre_trade_check(req, cfg, equity=equity,
                                         day_pnl_value=day_pnl_value,
                                         open_count=open_count)
    return PendingOrder(order_request=req, risk_check=check)
```

Note: `confirm_and_place` is unchanged. Because `req.stop_loss`/`req.target` are None,
its existing branch calls `dhan_client.place_order` (not bracket) — exactly what BTST needs.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_trade_controller_btst.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/trade_controller.py tests/test_trade_controller_btst.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): prepare_btst_order (CNC delivery, plan-based exit, two-step confirm)"
```

---

## Task 6: Journal BTST columns + open_btst_book

**Files:**
- Modify: `data/journal.py`
- Test: `tests/test_journal_btst.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_journal_btst.py`:
```python
from core.models import Instrument, OrderRequest, OrderResult, OrderType, Side, TradeMode
from data.journal import init_db, log_order, open_btst_book, list_trades


def _buy(sym="RELIANCE", qty=5):
    return OrderRequest(instrument=Instrument(symbol=sym, exchange_segment="NSE_EQ",
                                              security_id="1", kind="EQUITY"),
                        side=Side.BUY, order_type=OrderType.MARKET, qty=qty, price=100.0,
                        product_type="CNC")


def _sell(sym="RELIANCE", qty=5):
    return OrderRequest(instrument=Instrument(symbol=sym, exchange_segment="NSE_EQ",
                                              security_id="1", kind="EQUITY"),
                        side=Side.SELL, order_type=OrderType.MARKET, qty=qty, price=103.0,
                        product_type="CNC")


def _res(mode=TradeMode.PAPER):
    return OrderResult(ok=True, mode=mode, status="FILLED", dhan_order_id="O1",
                       exec_price=100.0)


def test_btst_columns_roundtrip(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy(), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    row = list_trades(conn)[0]
    assert row["strategy_tag"] == "BTST"
    assert row["planned_exit_date"] == "2026-07-15"
    assert row["plan_target"] == 103.0
    assert row["plan_stop"] == 98.0


def test_non_btst_order_has_null_tag(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy(), _res())          # existing-style call, no BTST kwargs
    row = list_trades(conn)[0]
    assert row["strategy_tag"] is None


def test_open_btst_book_lists_unclosed_buys(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy("RELIANCE"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    log_order(conn, _buy("TCS"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=50.0, plan_stop=45.0)
    book = open_btst_book(conn, mode="PAPER")
    syms = {b["symbol"] for b in book}
    assert syms == {"RELIANCE", "TCS"}
    reliance = next(b for b in book if b["symbol"] == "RELIANCE")
    assert reliance["plan_target"] == 103.0
    assert reliance["planned_exit_date"] == "2026-07-15"


def test_open_btst_book_excludes_closed_positions(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy("RELIANCE"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    log_order(conn, _sell("RELIANCE"), _res(), strategy_tag="BTST")   # closes it
    book = open_btst_book(conn, mode="PAPER")
    assert book == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal_btst.py -v`
Expected: FAIL — new columns/`open_btst_book` do not exist.

- [ ] **Step 3: Edit `data/journal.py`**

3a. Add the four columns to `_SCHEMA` (append inside the `CREATE TABLE` column list, before the closing `)`):
```python
  exit_price REAL, pnl REAL, rr_achieved REAL, closed_at TEXT,
  strategy_tag TEXT, planned_exit_date TEXT, plan_target REAL, plan_stop REAL
```

3b. In `init_db`, after `conn.execute(_SCHEMA)`, add an idempotent migration for pre-existing `trades.db` files that lack the columns:
```python
    conn.execute(_SCHEMA)
    _ensure_columns(conn)
    conn.commit()
    return conn
```
and add the helper:
```python
def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Additive migration for existing DBs — add BTST columns if missing."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(trades)")}
    for col, decl in (("strategy_tag", "TEXT"), ("planned_exit_date", "TEXT"),
                      ("plan_target", "REAL"), ("plan_stop", "REAL")):
        if col not in have:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {decl}")
```

3c. Extend `log_order`'s signature and row dict:
```python
def log_order(conn: sqlite3.Connection, req: OrderRequest, result: OrderResult,
              consensus=None, *, strategy_tag=None, planned_exit_date=None,
              plan_target=None, plan_stop=None) -> int:
```
and add to the `row` dict (before `cols = ...`):
```python
        "strategy_tag": strategy_tag, "planned_exit_date": planned_exit_date,
        "plan_target": plan_target, "plan_stop": plan_stop,
```

3d. Add `open_btst_book` at the end of the file:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_journal_btst.py -v`
Expected: 4 passed

- [ ] **Step 5: Confirm no regressions**

Run: `pytest tests/test_journal.py tests/ -q`
Expected: all green (new columns nullable; existing `log_order` calls unaffected).

- [ ] **Step 6: Commit**

```bash
git add data/journal.py tests/test_journal_btst.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): journal BTST plan columns + open_btst_book + additive migration"
```

---

## Task 7: BTST page (thin render, manual verify)

**Files:**
- Create: `pages/6_BTST.py`

This page only renders + delegates; it is verified by running, not unit-tested (all logic it calls is covered by Tasks 1–6). Follow the exact wiring patterns in `app.py` (imports, `get_client`, `get_journal`, `load_watchlist`, `get_equity`, risk panel, confirm dialog).

- [ ] **Step 1: Write `pages/6_BTST.py`**

```python
"""BTST (Buy Today, Sell Tomorrow) — near-close candidate scan + overnight book.
Thin render; all logic in services/btst, services/market_clock, trade_controller."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.models import Instrument, TradeMode
from core import config_store
from services import btst, market_clock, risk_manager, trade_controller, signal_engine
from services.dhan_client import DhanClient, DhanError
from services.strategies.engine import build_confluence
import services.strategies.trend        # noqa: F401  register strategies
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout     # noqa: F401
import services.strategies.volume       # noqa: F401
import services.strategies.structure    # noqa: F401
from data.journal import init_db, log_order, open_btst_book
from services import instruments
from ui import themes

load_dotenv()
st.set_page_config(page_title="BTST — Dhan-Claude Trader", layout="wide")
themes.apply()

ss = st.session_state
ss.setdefault("mode", config_store.get_setting("TRADE_MODE", "PAPER"))
ss.setdefault("btst_pending", None)


@st.cache_resource
def _journal():
    return init_db("trades.db")


def _client(mode: str) -> DhanClient:
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


@st.cache_resource
def _index():
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
                else instruments.download_master())
        return instruments.build_index(text)
    except Exception:                              # noqa: BLE001
        return {}


def _watchlist():
    data = json.loads(Path("watchlist.json").read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY")) for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, _index())


def _equity(mode: str, dhan: DhanClient) -> float:
    if mode == "LIVE":
        try:
            f = dhan.get_fund_limits()
            return float(f.get("availabelBalance", f.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


mode = ss["mode"]
cfg = risk_manager.load_risk_config({
    "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
    "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
    "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
})
journal = _journal()
dhan = _client(mode)
now = datetime.now(timezone.utc)

st.markdown(f"### BTST — Buy Today, Sell Tomorrow &nbsp; {'🟡 PAPER' if mode=='PAPER' else '🔴 LIVE'}")
st.caption("Scan near close · hold overnight · sell tomorrow · you confirm every trade")

# ---------------- candidates ----------------
st.markdown("#### Today's BTST candidates")
run_scan = market_clock.is_near_close(now)
if not run_scan:
    st.info("BTST scan runs 3:00–3:30 PM IST. You can dry-run a preview now.")
if run_scan or st.button("Scan now (preview)"):
    def candles_fn(instr):
        return dhan.get_candles(instr, interval="day", lookback_days=40)
    def confluence_fn(df):
        return build_confluence(df, regime=None, style="positional",
                                active_ids=list(range(1, 30)))
    try:
        candidates = btst.scan(_watchlist(), candles_fn=candles_fn,
                               confluence_fn=confluence_fn, active_ids=list(range(1, 30)))
    except DhanError as e:
        candidates = []
        st.warning(f"Scan failed: {e}")

    equity = _equity(mode, dhan)
    if not candidates:
        st.caption("No BTST candidates right now.")
    for c in candidates[:10]:
        with st.container():
            st.markdown(f"**{c.instrument.symbol}** · entry ₹{c.entry} · "
                        f"target ₹{c.target} · stop ₹{c.stop}")
            st.caption(" · ".join(c.reasons))
            st.error(f"⚠ {c.gap_risk}")
            if st.button(f"Select {c.instrument.symbol} →", key=f"btst_{c.instrument.symbol}"):
                ss["btst_pending"] = (c, trade_controller.prepare_btst_order(
                    c, equity=equity, cfg=cfg, day_pnl_value=0.0, open_count=0))

pending = ss.get("btst_pending")
if pending is not None:
    cand, po = pending

    @st.dialog("⚠ Confirm BTST Order — step 2 of 2")
    def _confirm():
        req = po.order_request
        st.write(f"**{req.instrument.symbol}** BUY {req.qty} @ ₹{req.price} (CNC delivery)")
        st.write(f"Plan: target ₹{cand.target} · stop ₹{cand.stop}")
        st.error(f"⚠ {cand.gap_risk}")
        if not po.risk_check.allowed:
            st.error("Blocked: " + "; ".join(po.risk_check.reasons))
        c1, c2 = st.columns(2)
        if c1.button("Place BTST Order", disabled=not po.risk_check.allowed):
            res = trade_controller.confirm_and_place(po, dhan_client=dhan,
                                                     journal_conn=journal)
            if res.ok:
                log_order(journal, req, res, strategy_tag="BTST",
                          planned_exit_date=str(market_clock.next_trading_day(now.date())),
                          plan_target=cand.target, plan_stop=cand.stop)
            st.toast(f"BTST: {res.status}")
            ss["btst_pending"] = None
            st.rerun()
        if c2.button("Cancel"):
            ss["btst_pending"] = None
            st.rerun()
    _confirm()

# ---------------- book ----------------
st.divider()
st.markdown("#### BTST Book — open overnight positions")
book = open_btst_book(journal, mode=mode)
if not book:
    st.caption("No open BTST positions.")
today = now.astimezone(market_clock.IST).date()
for b in book:
    due = b["planned_exit_date"] and str(today) >= b["planned_exit_date"]
    st.markdown(f"**{b['symbol']}** qty {b['qty']} · entry ₹{b['entry']} · "
                f"target ₹{b['plan_target']} · stop ₹{b['plan_stop']} · "
                f"exit {b['planned_exit_date']}")
    if due:
        st.warning("🔔 SELL reminder — planned exit day reached.")
        if st.button(f"Exit {b['symbol']} ✕", key=f"exit_{b['symbol']}"):
            instr = Instrument(symbol=b["symbol"],
                               exchange_segment=b["exchange_segment"],
                               security_id=str(b["security_id"]), kind="EQUITY")
            res = dhan.exit_position(instr)
            st.toast(f"Exit: {res.status}")
```

Note on the double-log: `confirm_and_place` already logs the order once (without BTST
tags). The page then calls `log_order` again with the BTST plan columns so the book can
find it. That means two rows for one placement. **Fix:** do NOT rely on
`confirm_and_place`'s internal log for BTST — instead pass the plan through. Simplest
correct approach: in the confirm handler, call `confirm_and_place` with
`journal_conn=None` (so it does not log), then do the single tagged `log_order` shown
above. Update the `_confirm` call to `trade_controller.confirm_and_place(po,
dhan_client=dhan, journal_conn=None)`.

- [ ] **Step 2: Manual verification**

Run: `streamlit run app.py` (the multipage app picks up `pages/6_BTST.py`), open the BTST page in the browser.
Checklist:
- Off-window: shows the "scan runs 3:00–3:30" info + working "Scan now (preview)" button.
- Preview lists candidates (or "No BTST candidates"); each card shows entry/target/stop, reasons, red gap-risk banner.
- "Select" opens the two-step confirm dialog; "Place BTST Order" in PAPER mode shows a toast and a single new row appears in the BTST Book with the correct plan + exit date (verify exactly one row via the Reports page / journal, confirming the `journal_conn=None` fix).
- BTST Book renders the open position; when the planned exit date is today/past, the SELL reminder + Exit button appear.

- [ ] **Step 3: Commit**

```bash
git add pages/6_BTST.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(btst): BTST page — candidate scan, two-step confirm, overnight book"
```

---

## Task 8: Full-suite gate + branch verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire suite**

Run: `pytest tests/ -q`
Expected: all green — the ~30 new BTST tests plus every pre-existing test (no regressions).

- [ ] **Step 2: Confirm the app still boots**

Run: `streamlit run app.py` — the main dashboard AND all pages (including the new BTST page) load without a traceback. Close it.

- [ ] **Step 3: If anything failed, fix and re-run before finishing.**

No commit needed unless a fix was made.

---

## Self-Review Notes

- **Spec coverage:** §2 modules → Tasks 1–7 (market_clock T1, models T2, btst T3, dhan_client T4, trade_controller T5, journal T6, page T7). §3 clock → T1. §4 scan + 4 filters + ATR plan + ranking → T3. §5 CNC path (product_type default preserved, plain place_order not bracket, segments already handles delivery) → T2/T4/T5. §6 journal columns + additive migration + open_btst_book → T6. §7 UI two sections → T7. §8 error handling → per-instrument skip (T3), off-window message (T7), gap risk always shown (T3/T7), DhanError surfaced (T7). §9 testing → each task is TDD; page manual.
- **Double-log hazard:** caught in T7 — `confirm_and_place` logs internally; BTST needs the plan columns, so the page passes `journal_conn=None` to `confirm_and_place` and does the single tagged `log_order` itself. Flagged explicitly so the implementer doesn't create two journal rows per BTST placement.
- **No-auto-fire preserved:** `confirm_and_place` unchanged; `prepare_btst_order` only prepares. Two-step confirm intact.
- **Type consistency:** `BtstCandidate` fields identical across T2/T3/T5/T7; `prepare_btst_order(candidate, *, equity, cfg, day_pnl_value, open_count)` matches T5 tests and T7 call; `log_order(..., *, strategy_tag, planned_exit_date, plan_target, plan_stop)` matches T6 tests and T7 call; `open_btst_book(conn, mode)` matches T6 and T7.
- **Deferred (documented):** holiday calendar (next_trading_day weekend-only) — belongs to the later "improvements" feature, per spec §3.
