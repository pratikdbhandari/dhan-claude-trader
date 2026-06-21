# Phase B3 — App + Risk + Two-Step Confirm Design

**Date:** 2026-06-21
**Status:** Approved
**Depends on:** B1 (dhan_client, journal), B2 (signal_engine), accounting engine

---

## 1. Purpose

The first runnable app: a `risk_manager` pre-trade gate, a UI-less `trade_controller`
two-step state machine (the no-auto-fire guarantee lives here, not in UI), and a thin
Streamlit `app.py` dashboard — signal cards, two-step confirm dialog, live positions
with one-click exit, risk monitor, auto-refresh.

**Principles:** All logic in testable plain functions; `app.py` only renders. An order
can ONLY fire through `trade_controller.confirm_and_place`, reachable solely from the
confirm dialog's second click. Risk limits unchanged (₹10k daily loss, 1%/trade, 2
open) — ask before changing.

---

## 2. risk_manager (`services/risk_manager.py`)

```python
@dataclass
class RiskConfig:
    max_daily_loss: float = 10000.0
    max_risk_per_trade_pct: float = 1.0
    max_open_positions: int = 2

def load_risk_config(env) -> RiskConfig   # from os.environ, defaults above
```

- `position_size(equity, entry, stop_loss, risk_pct) -> int`
  risk_amount = equity*risk_pct/100; per_share = abs(entry-stop_loss);
  qty = floor(risk_amount/per_share) (0 if per_share==0).
- `day_pnl(mode, dhan_client, journal_conn, ltp_fn) -> float`
  LIVE → sum realized+unrealized from `dhan_client.get_positions()`.
  PAPER → `accounting.pnl_statement(journal.to_legs(...), ...).total_pnl`.
- `open_position_count(mode, dhan_client, journal_conn) -> int`
  LIVE → count nonzero-net Dhan positions; PAPER → count of open holdings from accounting.
- `pre_trade_check(req, cfg, equity, day_pnl, open_count) -> RiskCheck`
  Blocks (collect ALL reasons) if:
  - `day_pnl <= -cfg.max_daily_loss` → "Daily loss limit reached"
  - `open_count >= cfg.max_open_positions` → "Max open positions"
  - trade risk `qty*|entry-stop| > equity*pct/100` → "Trade risk exceeds 1%"
  Returns `RiskCheck(allowed, reasons, day_pnl, open_positions, remaining_loss_buffer)`
  where buffer = `max_daily_loss + day_pnl` (floored at 0).

---

## 3. trade_controller (`services/trade_controller.py`)

UI-less two-step machine. **No method places an order except `confirm_and_place`.**

- `build_order_request(consensus, instrument, qty, order_type, mode) -> OrderRequest`
  Maps consensus (entry/SL/target/side from bias) into an OrderRequest.
- `prepare_order(consensus, instrument, equity, cfg, day_pnl, open_count, mode)
  -> PendingOrder` — computes qty via `position_size`, runs `pre_trade_check`, returns
  `PendingOrder(order_request, risk_check)`. Does NOT place.
- `confirm_and_place(pending, dhan_client, journal_conn, consensus) -> OrderResult`
  - If `pending.risk_check.allowed is False` → returns `OrderResult(ok=False,
    status="BLOCKED", error_message=reasons)` and logs nothing to the broker.
  - Else places via `dhan_client.place_order` (or `place_bracket_order` if SL+target),
    logs to journal, returns the OrderResult.

```python
@dataclass
class PendingOrder:
    order_request: OrderRequest
    risk_check: RiskCheck
```

---

## 4. app.py (thin Streamlit)

Renders only; all decisions delegate to the modules above. Layout:
- **Top banner:** 🟡 PAPER / 🔴 LIVE; toggles for trade-mode + signal-source (mock|api);
  manual refresh button; auto-refresh every 5 min (native: store last-refresh ts in
  `st.session_state`, `st.rerun()` when elapsed).
- **Signal cards** (per watchlist instrument): consensus signal, confidence meter,
  per-provider chips, entry/SL/target, R:R, reasoning. "Select" sets
  `st.session_state.pending = prepare_order(...)`.
- **Confirm dialog** (`st.dialog`): full order details + risk_check result. Two buttons:
  "Place Order" → `confirm_and_place(...)`; "Cancel" → clears pending. This is the ONLY
  path to placement.
- **Risk monitor:** today P&L, loss buffer, exposure %, open positions; if
  `not risk_check.allowed` globally (e.g. daily loss breached) → confirm disabled +
  reason shown.
- **Positions table:** live from `dhan_client.get_positions`; per-row "Exit" →
  `dhan_client.exit_position`.
- Custom CSS injected for the dark theme (approximation of the mockup).

`st.session_state` keys: `mode`, `signal_source`, `pending`, `last_refresh`,
`signal_cache` (passed to `signal_engine.generate`).

---

## 5. Data Flow

```
watchlist → signal_engine.generate(mode=source, cache) → ConsensusSignal → card
[Select] → trade_controller.prepare_order(consensus, equity, day_pnl, open_count)
        → PendingOrder(order_request, risk_check) → st.session_state.pending
[dialog "Place Order"] → trade_controller.confirm_and_place(pending, dhan, journal)
        → dhan place + journal.log_order → OrderResult
risk panel ← risk_manager.day_pnl / open_position_count
positions ← dhan_client.get_positions ; [Exit] → dhan_client.exit_position
equity ← dhan_client.get_fund_limits (LIVE) | ACCOUNT_CAPITAL env (PAPER)
```

---

## 6. Error / Edge Handling

- Risk-blocked order → never reaches broker; UI shows reasons.
- `day_pnl`/positions read failure (DhanError) → surfaced in UI banner; cards still render.
- qty==0 from position_size (entry==stop) → prepare_order returns risk_check blocked
  ("invalid stop").
- HOLD consensus → no "Select" button (nothing to place).
- PAPER mode → place_order simulated (B1), journal logs, accounting updates.

---

## 7. Testing (TDD; app.py manual)

- `risk_manager`: position_size math; each pre_trade_check block reason fires
  independently and in combination; day_pnl PAPER path via fake journal+accounting;
  buffer calc.
- `trade_controller`: prepare_order builds request + runs gate; `confirm_and_place`
  places + logs when allowed; returns BLOCKED + places nothing when risk_check denied;
  two-step proven (prepare never places). Inject fake dhan_client + temp journal.
- `app.py`: NOT unit-tested — verified by `streamlit run app.py` (manual checklist in
  plan). Logic it calls is fully covered above.

---

## 8. Out of Scope (B4 / later)

EOD report, accounting UI page (B4). Accuracy-weighted consensus, event guards (C).
No order-status polling. No real-key live trading verification in this slice (PAPER is
the default and the tested path).
