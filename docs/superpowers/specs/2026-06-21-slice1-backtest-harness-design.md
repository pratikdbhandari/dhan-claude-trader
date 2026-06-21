# Slice 1 — Backtest Harness + Profit-Probability Calibration

**Date:** 2026-06-21
**Status:** Approved
**Depends on:** strategy engine (build_confluence), regime, charges, indicators

---

## 1. Purpose

A pure historical-replay backtester for the mechanical technical engine (29 strategies →
regime → confluence), with ATR-based exits, charge-accurate P&L, walk-forward
out-of-sample evaluation, and a **calibration table** that turns backtested outcomes
into an honest **Profit-Probability score** (realized win-rate per setup bucket).

**Honest framing:** backtests the deterministic technical engine, NOT the LLM layer
(calling AI over thousands of bars is costly/non-reproducible). It answers: does the
core engine have edge before we layer fundamentals/news/sizing on top? Out-of-sample is
the reality check. Profit-Probability = empirical historical win-rate for similar setups
— never the LLM's self-reported confidence (which stays shown but labeled uncalibrated).

---

## 2. Data Types (extend `core/models.py`)

```python
@dataclass
class BacktestTrade:
    symbol: str
    side: str                 # BUY | SELL
    entry_idx: int
    exit_idx: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    charges: float
    net_pnl: float
    exit_reason: str          # STOP | TARGET | TIME
    regime: str
    net_score: float

@dataclass
class BacktestResult:
    trades: list[BacktestTrade]
    n_trades: int
    wins: int
    win_rate: float
    gross_pnl: float
    net_pnl: float
    profit_factor: float      # gross_profit / gross_loss (inf if no losses)
    expectancy: float         # net_pnl / n_trades
    max_drawdown: float       # worst peak-to-trough on cumulative net P&L
    calibration: list[dict]   # buckets: {regime, score_band, n, win_rate}
```

---

## 3. backtest.py (`services/backtest.py`, pure)

- `simulate(df, *, active_ids, style, segment, atr_sl=1.0, atr_tgt=2.0, time_cap=20,
  warmup=200, qty=1) -> BacktestResult`:
  - Walk `i` from `warmup` to len-1. If no open trade, `build_confluence(df.iloc[:i+1],
    regime=None, style, active_ids)` → bias. On BUY/SELL: open at `close[i]`, ATR from
    `indicators.atr`; stop = entry ∓ atr_sl*ATR, target = entry ± atr_tgt*ATR (sign by side).
  - While a trade is open, scan bars `i+1..`: exit when high/low crosses target/stop
    (target checked first if both in one bar is ambiguous → assume stop first =
    conservative), or after `time_cap` bars → exit at that close, reason TIME.
  - Charges via `charges.compute` on entry+exit (segment-aware). net = gross − charges.
  - No pyramiding: one open trade at a time per run.
- Metrics computed from the trade list (win_rate, profit_factor, expectancy, max_drawdown).
- `calibration`: bucket trades by `(regime, score_band)` where score_band ∈
  {"0.15-0.30","0.30-0.50","0.50+"} on `abs(net_score)`; each bucket → `{n, win_rate}`.

- `split_eval(df, *, train_frac=0.7, **kw) -> dict`:
  - Run `simulate` on `df.iloc[:cut]` (in-sample) and `df.iloc[cut:]` (out-of-sample);
    return `{"in_sample": BacktestResult, "out_of_sample": BacktestResult}`. Divergence
    between the two flags overfitting/regime-dependence.

- `profit_probability(net_score, regime, calibration) -> float | None`:
  - Look up the matching bucket's win_rate; None if no bucket / too few samples (n<5).

---

## 4. backtest_data.py (`services/backtest_data.py`, thin)

- `load_candles(instrument, interval, lookback_days, *, dhan_client=None,
  cache_dir="data/backtest") -> DataFrame`:
  - If cached CSV exists, load it; else `dhan_client.get_candles(...)`, cache to CSV.
  - Injectable client for tests; cache keeps repeat runs offline + fast.

---

## 5. Runner (`scripts_backtest.py`, manual)

Loads watchlist (resolved), for each instrument + each preset: `split_eval`, prints a
table of in-sample vs out-of-sample metrics + calibration, writes
`reports/backtest_<symbol>_<preset>.md`. Read-only, no orders.

---

## 6. Profit-Probability surfacing (light)

`backtest` can `save_calibration(result, path="data/calibration.json")`. `signal_engine`
optionally loads it and attaches `profit_probability` to the ConsensusSignal
`indicator_snapshot` (best-effort; absent if no calibration file). UI shows it as
"Profit Probability (historical, N samples)" beside the uncalibrated model confidence.
Wiring into the live card is minimal and optional in this slice.

---

## 7. Error / Edge Handling

- `df` shorter than `warmup` → empty result (0 trades, zeroed metrics).
- No losing trades → profit_factor = inf (rendered as "∞").
- ATR NaN at a bar → skip entry that bar.
- Bucket with n<5 → profit_probability returns None (don't over-claim on thin data).
- Both stop and target inside one bar → assume STOP (conservative).

---

## 8. Testing (TDD; runner manual)

- `simulate`: synthetic trending fixture → trades generated; net < gross (charges);
  a constructed stop-hit and target-hit case exit with correct reason; time_cap forces
  exit; metrics (win_rate, profit_factor, expectancy, max_drawdown) on a known trade set.
- `split_eval`: returns two BacktestResults; cut index correct.
- `profit_probability`: bucket lookup; None when n<5 / no match.
- `backtest_data`: cached CSV path used when present; fetch+cache when absent (fake client).

---

## 9. Out of Scope

LLM-in-the-loop backtest, multi-position/pyramiding, slippage modelling beyond charges,
parameter optimization/auto-tuning (we report, we don't curve-fit), options backtest.
Tri-Factor gate and sizing are later slices that this validates.
