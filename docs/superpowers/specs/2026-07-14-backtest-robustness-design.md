# Backtest Robustness Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/backtest.py` (`simulate`, `_result`, `BacktestResult`, `split_eval`), `core/models.BacktestResult/BacktestTrade`, `services/charting`, `ui/themes`, `services/instruments`, `services/dhan_client`.
**Origin:** Vibe-Trading review pick #2 — directly addresses the project's own stated gap ("no backtest validation; guard against curve-fitting").

---

## 1. Purpose

Add three validation methods on top of the existing single-shot backtest so a strategy's
edge can be stress-tested before trusting it with capital, and surface them on a new
in-app Backtest page:

- **Walk-forward** — evaluate out-of-sample across multiple sequential windows, not one
  split; checks the edge holds across time (anti-curve-fit).
- **Monte Carlo drawdown** — shuffle trade order many times; distribution of max drawdown
  (how bad the equity dip can get by ordering luck).
- **Bootstrap CI** — resample trades with replacement; confidence interval on expectancy
  (is the average edge real or noise?).

**Principles:** pure, seeded (deterministic) functions, unit-tested; the page only
renders. Honest framing: this reduces curve-fit risk, it does not eliminate it.

**Out of scope:** parameter optimization/search, cross-instrument portfolio backtests,
changing `simulate`'s signal logic, options backtests.

---

## 2. Module (`services/backtest_robust.py`, new, pure)

```python
def walk_forward(df, *, n_splits: int = 4, min_test: int = 50, sim_kwargs: dict) -> dict
def monte_carlo_drawdown(result, *, n: int = 1000, seed: int = 0) -> dict
def bootstrap_ci(result, *, n: int = 1000, seed: int = 0) -> dict
def robustness_verdict(wf: dict, mc: dict, ci: dict) -> dict
```

**walk_forward(df, *, n_splits, min_test, sim_kwargs):**
Split `df` into `n_splits` contiguous, non-overlapping test windows after a shared warmup
region (the engine needs `warmup` bars before it trades — reuse `sim_kwargs["warmup"]` or
default 200). For each window, call `simulate(window_df, **sim_kwargs)` and collect its
`BacktestResult` metrics. Windows with `< min_test` bars are skipped. Returns:
```python
{"folds": [{"net_pnl", "win_rate", "expectancy", "profit_factor",
            "max_drawdown", "n_trades"}...],
 "n_folds": int,
 "mean_expectancy": float,
 "pct_folds_profitable": float,   # % of folds with net_pnl > 0
 "insufficient": bool}            # True if < 2 usable folds
```
Because `simulate` derives signals from data alone (no fitted parameters), sequential
OOS windows are the temporal-consistency test — a genuine edge should stay profitable in
most windows, a curve-fit one won't.

**monte_carlo_drawdown(result, *, n, seed):**
Take `result.trades`' `net_pnl` sequence. With a seeded `random.Random(seed)`, shuffle the
order `n` times; for each ordering compute max drawdown on the cumulative curve (same
formula as `backtest._result`). Return:
```python
{"mean": float, "p50": float, "p95": float, "worst": float, "insufficient": bool}
```
`insufficient=True` (and zeros) when `< 10` trades.

**bootstrap_ci(result, *, n, seed):**
Seeded resample of `net_pnl` with replacement (same length as the trade list), `n` times;
each replicate's expectancy = mean(net_pnl). Return:
```python
{"mean": float, "lo": float, "hi": float, "insufficient": bool}
```
`lo`/`hi` = 2.5th / 97.5th percentiles. `insufficient=True` when `< 10` trades.

**robustness_verdict(wf, mc, ci):**
Combine into a plain verdict: `robust` when `wf["pct_folds_profitable"] >= 60` AND
`ci["lo"] > 0` AND not any `insufficient`. Returns
`{"robust": bool, "reasons": [str, ...]}` explaining each factor (e.g. "62% of folds
profitable", "expectancy CI [12, 47] excludes zero", "p95 drawdown ₹3,200"). Honest note
included: not a guarantee.

---

## 3. Page (`pages/7_Backtest.py`, thin, manual-verify)

Controls: instrument selectbox (from watchlist), preset selectbox (from `strategies.json`
active_ids), lookback slider. On "Run backtest":
- fetch candles (`dhan.get_candles`, long lookback), `simulate(...)` → `BacktestResult`;
- run `walk_forward`, `monte_carlo_drawdown`, `bootstrap_ci`, `robustness_verdict`;
- render: headline verdict (green/amber), the base result metrics, a walk-forward
  fold bar chart (expectancy per fold), MC drawdown percentile metrics + a histogram,
  bootstrap expectancy CI as a labeled range. Charts use `themes.chart_colors()`.

If `simulate` returns `< 10` trades → show "insufficient trades to validate; widen the
lookback or loosen the preset" and skip the robustness panels (no fake numbers).

## 4. Charting additions (`services/charting.py`)

- `fold_bars(folds, colors=None)` — expectancy per walk-forward fold (green≥0 / signal<0).
- `histogram(values, colors=None, title="")` — generic themed histogram (MC drawdowns).
Both pure, return `go.Figure`, empty-input safe (annotated empty figure).

## 5. Error / edge handling

- `< 10` trades → every robustness fn returns `insufficient=True` with zeroed stats; page
  shows the guidance message, no panels.
- `< 2` usable walk-forward folds → `wf["insufficient"]=True`; verdict cannot be "robust".
- Seeded RNG → identical results on re-run (reproducible, testable).
- Short `df` → fewer/zero folds, not a crash.
- `DhanError` on candle fetch → surfaced banner; page still renders controls.

## 6. Testing

- `monte_carlo_drawdown`: on a known trade list with fixed seed, assert `mean`/`p95`/`worst`
  are the expected reproducible values; `< 10` trades → `insufficient`.
- `bootstrap_ci`: fixed seed → reproducible `mean`/`lo`/`hi`; `lo <= mean <= hi`; `< 10`
  trades → `insufficient`.
- `walk_forward`: synthetic trending df → returns `n_folds` folds with the metric keys;
  `pct_folds_profitable` in [0, 100]; too-short df → `insufficient`.
- `robustness_verdict`: robust when all three pass; not robust if CI lo ≤ 0 / folds < 60% /
  any insufficient; reasons list non-empty.
- `charting.fold_bars` / `charting.histogram`: return `go.Figure`; empty input safe.
- Page verified by running.
