# Behavior Diagnostics — Disposition Effect Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/accounting.realized_trades` (returns `list[RealizedTrade]`), `data/journal.to_legs`, `pages/1_Reports.py`.
**Origin:** first pick from the Vibe-Trading (HKUDS) feature review — journal behavior diagnostics. Concept adopted; code written fresh in this repo's style (no code copied).
**Scope:** disposition effect only. Other diagnostics (overtrading, plan discipline, revenge trading) are deliberately deferred to keep this a single small slice.

---

## 1. Purpose

Turn the existing trade journal into behavioral feedback: detect the **disposition
effect** — the tendency to hold losing trades longer than winners (ride losers, cut
winners) — and surface it on the Reports page with the numbers and a plain-language
verdict.

**Principles carried over:** pure unit-tested logic; the page only renders; PAPER and
LIVE books are separate (mode flows through as everywhere else).

**Out of scope:** overtrading/churn, R:R plan-discipline, revenge trading (future
diagnostics), any change to how trades are recorded, and any new data source. This
reads only what `accounting.realized_trades` already produces.

---

## 2. Module (`services/behavior.py`, new)

```python
@dataclass
class DispositionResult:
    n_wins: int
    n_losses: int
    avg_hold_win_hours: float
    avg_hold_loss_hours: float
    avg_win: float                 # mean net_pnl of winners (> 0)
    avg_loss: float                # mean net_pnl of losers (< 0, reported as a positive magnitude)
    hold_ratio: float              # avg_hold_loss_hours / avg_hold_win_hours (0.0 if win-hold is 0)
    present: bool                  # True when losers are held longer than winners
    insufficient: bool            # True when < MIN_SAMPLE wins or losses
    verdict: str                   # human-readable summary

def disposition_effect(trades: list[RealizedTrade]) -> DispositionResult: ...
```

**Constant:** `MIN_SAMPLE = 3` (need at least 3 winners AND 3 losers to say anything).

**Algorithm:**
1. For each trade, compute `hold_hours = (parse(closed_at) - parse(opened_at)).total_seconds() / 3600`. Timestamps are ISO strings (`datetime.fromisoformat`). If either is missing/unparseable, skip that trade (do not crash).
2. Classify: `net_pnl > 0` → winner; `net_pnl < 0` → loser; `== 0` → dropped.
3. If `n_wins < MIN_SAMPLE` or `n_losses < MIN_SAMPLE`: return `insufficient=True`, `present=False`, verdict = "Not enough closed trades yet (need ≥3 wins and ≥3 losses) to assess disposition effect."
4. Otherwise compute `avg_hold_win_hours`, `avg_hold_loss_hours`, `avg_win` (mean of winner net_pnl), `avg_loss` (mean magnitude of loser net_pnl), `hold_ratio = avg_hold_loss_hours / avg_hold_win_hours` (0.0 guard when the denominator is 0).
5. `present = avg_hold_loss_hours > avg_hold_win_hours`.
6. Verdict:
   - present → "Disposition effect detected: losers held {avg_hold_loss_hours:.1f}h vs winners {avg_hold_win_hours:.1f}h ({hold_ratio:.1f}× longer). You tend to ride losers and cut winners."
   - not present → "No disposition effect: winners held {avg_hold_win_hours:.1f}h vs losers {avg_hold_loss_hours:.1f}h — you are not systematically riding losers."

The magnitude comparison (`avg_win` vs `avg_loss`) is reported as context in the
result but the `present` flag keys off hold time, which is the direct disposition
signal.

---

## 3. UI (`pages/1_Reports.py`)

Add a "Behavior" expander (near the existing P&L / EOD sections), for the currently
selected mode:

```
legs   = to_legs(journal, mode)
trades = accounting.realized_trades(legs, mode)
result = behavior.disposition_effect(trades)
```

Render: if `insufficient` → show the verdict caption only. Else show the verdict
(colored: warning if `present`, success if not), plus a small metrics row —
winners: n / avg hold h / avg ₹; losers: n / avg hold h / avg ₹; hold ratio.

No change to any other Reports section.

---

## 4. Error / Edge Handling

- Unparseable/missing timestamp on a trade → that trade skipped, computation continues.
- Fewer than MIN_SAMPLE wins or losses → `insufficient`, friendly message, no false verdict.
- Zero-P&L trades dropped (neither win nor loss).
- `avg_hold_win_hours == 0` (all winners same-second open/close, e.g. PAPER fills) →
  `hold_ratio = 0.0` guard, no ZeroDivisionError.
- Empty trade list → `insufficient` (n_wins = n_losses = 0).

---

## 5. Testing (TDD, existing pytest style)

- Losers held longer than winners (≥3 each) → `present=True`, correct hold averages and ratio.
- Winners held longer / equal → `present=False`.
- 2 wins or 2 losses → `insufficient=True`, `present=False`.
- Empty list → `insufficient=True`.
- Hold-hours math: a trade opened 09:00 closed 13:00 → 4.0h.
- Bad/missing timestamp on one trade → skipped, rest still computed.
- Zero-P&L trade excluded from both counts.
- `avg_hold_win_hours == 0` → `hold_ratio == 0.0`, no crash.
- Reports page verified by running, not unit-tested.
