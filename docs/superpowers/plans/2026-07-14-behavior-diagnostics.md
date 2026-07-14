# Behavior Diagnostics (Disposition Effect) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect the disposition effect (holding losers longer than winners) from the existing trade journal and show it on the Reports page.

**Architecture:** One new pure module `services/behavior.py` computes a `DispositionResult` from `list[RealizedTrade]` (already produced by `accounting.realized_trades`); `pages/1_Reports.py` gains a "Behavior" expander that renders it. No new data, no new deps, no change to how trades are recorded.

**Tech Stack:** Python 3.13 stdlib (`datetime`, `dataclasses`), Streamlit, pytest — all in the repo.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-behavior-diagnostics-design.md`](../specs/2026-07-14-behavior-diagnostics-design.md)

---

## Before You Start

- Branch `feature/btst-signals` is current. Behavior diagnostics is independent of BTST; either create `feature/behavior-diagnostics` off `master` or continue on the current branch per your integration preference. Commits use inline identity: `git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "..."`.
- Read `core/models.py` `RealizedTrade` (fields: symbol, segment, mode, qty, buy_price, sell_price, gross_pnl, charges, net_pnl, rr_predicted, rr_achieved, opened_at, closed_at — the last two are ISO strings) and `services/accounting.py` `realized_trades(legs, mode)`.
- Read `pages/1_Reports.py` (it already builds `journal`, `mode`, `legs`; imports `to_legs`, `pnl_statement`).

---

## Task 1: behavior.disposition_effect

**Files:**
- Create: `services/behavior.py`
- Test: `tests/test_behavior.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_behavior.py`:
```python
from core.models import RealizedTrade
from services.behavior import disposition_effect, DispositionResult, MIN_SAMPLE


def _t(net_pnl, opened, closed):
    """RealizedTrade with only the fields disposition_effect reads meaningfully."""
    return RealizedTrade(
        symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
        buy_price=100.0, sell_price=100.0 + net_pnl, gross_pnl=net_pnl, charges=0.0,
        net_pnl=net_pnl, rr_predicted=None, rr_achieved=None,
        opened_at=opened, closed_at=closed)


def _hours_apart(base_day, open_h, hold_h):
    o = f"2026-07-{base_day:02d}T{open_h:02d}:00:00"
    close_h = open_h + hold_h
    c = f"2026-07-{base_day:02d}T{close_h:02d}:00:00"
    return o, c


def test_disposition_present_when_losers_held_longer():
    trades = []
    # 3 winners held 1h each
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(+50.0, o, c))
    # 3 losers held 5h each
    for d in (4, 5, 6):
        o, c = _hours_apart(d, 9, 5)
        trades.append(_t(-40.0, o, c))
    r = disposition_effect(trades)
    assert isinstance(r, DispositionResult)
    assert r.insufficient is False
    assert r.present is True
    assert r.n_wins == 3 and r.n_losses == 3
    assert r.avg_hold_win_hours == 1.0
    assert r.avg_hold_loss_hours == 5.0
    assert r.hold_ratio == 5.0
    assert r.avg_win == 50.0
    assert r.avg_loss == 40.0        # magnitude
    assert "detected" in r.verdict.lower()


def test_no_disposition_when_winners_held_longer():
    trades = []
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 5)
        trades.append(_t(+50.0, o, c))
    for d in (4, 5, 6):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(-40.0, o, c))
    r = disposition_effect(trades)
    assert r.present is False
    assert "no disposition" in r.verdict.lower()


def test_insufficient_when_too_few_losses():
    trades = []
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(+50.0, o, c))
    o, c = _hours_apart(4, 9, 5)
    trades.append(_t(-40.0, o, c))     # only 1 loss < MIN_SAMPLE
    r = disposition_effect(trades)
    assert r.insufficient is True
    assert r.present is False
    assert "enough" in r.verdict.lower()


def test_empty_list_is_insufficient():
    r = disposition_effect([])
    assert r.insufficient is True
    assert r.n_wins == 0 and r.n_losses == 0


def test_hold_hours_math():
    # 09:00 -> 13:00 = 4h for winners, 09:00 -> 11:00 = 2h for losers
    trades = [_t(+10.0, *(_hours_apart(d, 9, 4))) for d in (1, 2, 3)]
    trades += [_t(-10.0, *(_hours_apart(d, 9, 2))) for d in (4, 5, 6)]
    r = disposition_effect(trades)
    assert r.avg_hold_win_hours == 4.0
    assert r.avg_hold_loss_hours == 2.0


def test_bad_timestamp_trade_skipped():
    good = [_t(+50.0, *(_hours_apart(d, 9, 1))) for d in (1, 2, 3)]
    good += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    bad = _t(+50.0, "not-a-date", "also-bad")
    r = disposition_effect(good + [bad])
    assert r.n_wins == 3               # bad winner skipped, not counted
    assert r.insufficient is False


def test_zero_pnl_trade_excluded():
    trades = [_t(+50.0, *(_hours_apart(d, 9, 1))) for d in (1, 2, 3)]
    trades += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    trades.append(_t(0.0, *(_hours_apart(7, 9, 3))))    # breakeven, dropped
    r = disposition_effect(trades)
    assert r.n_wins == 3 and r.n_losses == 3


def test_zero_win_hold_ratio_guard():
    # winners open==close (0h hold, e.g. same-second PAPER fills)
    trades = [_t(+50.0, f"2026-07-0{d}T09:00:00", f"2026-07-0{d}T09:00:00")
              for d in (1, 2, 3)]
    trades += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    r = disposition_effect(trades)
    assert r.avg_hold_win_hours == 0.0
    assert r.hold_ratio == 0.0         # no ZeroDivisionError
    assert r.present is True            # losers (5h) held longer than winners (0h)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_behavior.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.behavior'`

- [ ] **Step 3: Write `services/behavior.py`**

```python
"""Trading-behavior diagnostics over closed trades. Pure: RealizedTrade list in,
DispositionResult out. First diagnostic: the disposition effect (holding losers
longer than winners). Concept adapted from the Vibe-Trading project; implemented
fresh in this repo's style."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from core.models import RealizedTrade

MIN_SAMPLE = 3


@dataclass
class DispositionResult:
    n_wins: int
    n_losses: int
    avg_hold_win_hours: float
    avg_hold_loss_hours: float
    avg_win: float
    avg_loss: float               # positive magnitude
    hold_ratio: float             # avg_hold_loss / avg_hold_win (0.0 if win-hold is 0)
    present: bool
    insufficient: bool
    verdict: str


def _hold_hours(trade: RealizedTrade) -> float | None:
    try:
        o = datetime.fromisoformat(trade.opened_at)
        c = datetime.fromisoformat(trade.closed_at)
    except (ValueError, TypeError):
        return None
    return (c - o).total_seconds() / 3600.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def disposition_effect(trades: list[RealizedTrade]) -> DispositionResult:
    win_holds: list[float] = []
    loss_holds: list[float] = []
    wins: list[float] = []
    losses: list[float] = []
    for t in trades:
        h = _hold_hours(t)
        if h is None:
            continue
        if t.net_pnl > 0:
            win_holds.append(h)
            wins.append(t.net_pnl)
        elif t.net_pnl < 0:
            loss_holds.append(h)
            losses.append(-t.net_pnl)          # store as magnitude
        # net_pnl == 0 dropped

    n_wins, n_losses = len(wins), len(losses)
    avg_hold_win = round(_mean(win_holds), 2)
    avg_hold_loss = round(_mean(loss_holds), 2)
    avg_win = round(_mean(wins), 2)
    avg_loss = round(_mean(losses), 2)

    if n_wins < MIN_SAMPLE or n_losses < MIN_SAMPLE:
        return DispositionResult(
            n_wins=n_wins, n_losses=n_losses, avg_hold_win_hours=avg_hold_win,
            avg_hold_loss_hours=avg_hold_loss, avg_win=avg_win, avg_loss=avg_loss,
            hold_ratio=0.0, present=False, insufficient=True,
            verdict=(f"Not enough closed trades yet (need ≥{MIN_SAMPLE} wins and "
                     f"≥{MIN_SAMPLE} losses) to assess disposition effect."))

    hold_ratio = round(avg_hold_loss / avg_hold_win, 2) if avg_hold_win > 0 else 0.0
    present = avg_hold_loss > avg_hold_win
    if present:
        verdict = (f"Disposition effect detected: losers held {avg_hold_loss:.1f}h vs "
                   f"winners {avg_hold_win:.1f}h ({hold_ratio:.1f}× longer). You tend "
                   f"to ride losers and cut winners.")
    else:
        verdict = (f"No disposition effect: winners held {avg_hold_win:.1f}h vs losers "
                   f"{avg_hold_loss:.1f}h — you are not systematically riding losers.")

    return DispositionResult(
        n_wins=n_wins, n_losses=n_losses, avg_hold_win_hours=avg_hold_win,
        avg_hold_loss_hours=avg_hold_loss, avg_win=avg_win, avg_loss=avg_loss,
        hold_ratio=hold_ratio, present=present, insufficient=False, verdict=verdict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_behavior.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add services/behavior.py tests/test_behavior.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(behavior): disposition-effect diagnostic over closed trades"
```

---

## Task 2: Reports page "Behavior" expander (manual verify)

**Files:**
- Modify: `pages/1_Reports.py`

Thin render; verified by running. All logic is covered by Task 1.

- [ ] **Step 1: Add imports**

At the top of `pages/1_Reports.py`, alongside the existing accounting imports, add:
```python
from services.accounting import realized_trades
from services import behavior
```
(`pnl_statement` / `to_legs` imports are already present — keep them.)

- [ ] **Step 2: Add the Behavior expander**

After the existing P&L section (anywhere below where `legs` and `mode` are defined), add:

```python
# ---- Behavior diagnostics
with st.expander("🧠 Behavior — disposition effect", expanded=False):
    _trades = realized_trades(legs, mode)
    _disp = behavior.disposition_effect(_trades)
    if _disp.insufficient:
        st.caption(_disp.verdict)
    else:
        if _disp.present:
            st.warning(_disp.verdict)
        else:
            st.success(_disp.verdict)
        b1, b2, b3 = st.columns(3)
        b1.metric("Winners", f"{_disp.n_wins}",
                  help=f"avg hold {_disp.avg_hold_win_hours:.1f}h · avg ₹{_disp.avg_win:,.0f}")
        b2.metric("Losers", f"{_disp.n_losses}",
                  help=f"avg hold {_disp.avg_hold_loss_hours:.1f}h · avg ₹{_disp.avg_loss:,.0f}")
        b3.metric("Loss/Win hold ratio", f"{_disp.hold_ratio:.1f}×")
```

- [ ] **Step 3: Manual verification**

Run: `streamlit run app.py`, open the Reports page, expand "Behavior — disposition effect".
- With < 3 wins or < 3 losses in the selected book: shows the "not enough closed trades" caption.
- Switch Book PAPER/LIVE: recomputes for that book.
- With enough trades (place a few PAPER round-trips first, or use an existing populated book): shows the colored verdict + the three metrics; warning color when the effect is present, success when not.

- [ ] **Step 4: Commit**

```bash
git add pages/1_Reports.py
git -c user.name="Pratik Bhandari" -c user.email="capratikbhandari@gmail.com" commit -m "feat(behavior): Reports page disposition-effect expander"
```

---

## Task 3: Full-suite gate

**Files:** none.

- [ ] **Step 1: Run the entire suite**

Run: `pytest tests/ -q`
Expected: all green — 8 new behavior tests plus every pre-existing test.

- [ ] **Step 2: Confirm the app boots**

Run: `streamlit run app.py` — Reports page loads with the new expander, no traceback. Close it. Fix and re-run if anything fails.

---

## Self-Review Notes

- **Spec coverage:** §2 module/model/algorithm → Task 1 (MIN_SAMPLE=3, ISO parse, win/loss classify, hold_ratio zero-guard, present-by-hold-time, both verdict branches). §3 UI expander → Task 2. §4 edges → Task 1 tests (bad timestamp skipped, zero-pnl dropped, empty→insufficient, zero-win-hold guard). §5 testing → Task 1 TDD; page manual.
- **No placeholders**; all code shown in full.
- **Type consistency:** `DispositionResult` fields identical between spec, impl, and tests; `disposition_effect(trades: list[RealizedTrade]) -> DispositionResult` matches the Task 2 call `behavior.disposition_effect(realized_trades(legs, mode))`; `MIN_SAMPLE` referenced in both impl and tests.
- **YAGNI:** only disposition effect; other diagnostics deferred per spec scope.
