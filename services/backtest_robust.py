"""Backtest robustness checks — pure, seeded (deterministic) validation over an
existing BacktestResult / candle frame. Reduces curve-fit risk; does not remove it."""
from __future__ import annotations
import random
import statistics

MIN_TRADES = 10


def _max_drawdown(nets: list[float]) -> float:
    cum, peak, mdd = 0.0, 0.0, 0.0
    for x in nets:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return round(mdd, 2)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def monte_carlo_drawdown(result, *, n: int = 1000, seed: int = 0) -> dict:
    """Shuffle trade order n times; distribution of max drawdown."""
    nets = [t.net_pnl for t in result.trades]
    if len(nets) < MIN_TRADES:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "worst": 0.0, "insufficient": True}
    rng = random.Random(seed)
    dds = []
    for _ in range(n):
        order = nets[:]
        rng.shuffle(order)
        dds.append(_max_drawdown(order))
    dds.sort()
    return {"mean": round(statistics.mean(dds), 2), "p50": _pct(dds, 0.50),
            "p95": _pct(dds, 0.95), "worst": max(dds), "insufficient": False}


def bootstrap_ci(result, *, n: int = 1000, seed: int = 0) -> dict:
    """Resample net_pnl with replacement; 95% CI on expectancy (mean net_pnl)."""
    nets = [t.net_pnl for t in result.trades]
    if len(nets) < MIN_TRADES:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "insufficient": True}
    rng = random.Random(seed)
    k = len(nets)
    means = []
    for _ in range(n):
        sample = [nets[rng.randrange(k)] for _ in range(k)]
        means.append(statistics.mean(sample))
    means.sort()
    return {"mean": round(statistics.mean(means), 2),
            "lo": round(_pct(means, 0.025), 2), "hi": round(_pct(means, 0.975), 2),
            "insufficient": False}


def walk_forward(df, *, n_splits: int = 4, min_test: int = 50,
                 sim_kwargs: dict) -> dict:
    """Evaluate simulate() over n_splits contiguous out-of-sample windows.
    Each window includes the shared warmup lead-in the engine needs. A genuine
    edge stays profitable across most windows; a curve-fit one won't."""
    from services.backtest import simulate
    warmup = int(sim_kwargs.get("warmup", 200))
    n = len(df)
    usable = n - warmup
    folds = []
    if usable > 0 and n_splits > 0:
        seg = usable // n_splits
        for i in range(n_splits):
            start = warmup + i * seg
            end = n if i == n_splits - 1 else warmup + (i + 1) * seg
            window = df.iloc[max(0, start - warmup):end]
            if end - start < min_test:
                continue
            res = simulate(window, **sim_kwargs)
            folds.append({"net_pnl": res.net_pnl, "win_rate": res.win_rate,
                          "expectancy": res.expectancy,
                          "profit_factor": res.profit_factor,
                          "max_drawdown": res.max_drawdown, "n_trades": res.n_trades})
    if len(folds) < 2:
        return {"folds": folds, "n_folds": len(folds), "mean_expectancy": 0.0,
                "pct_folds_profitable": 0.0, "insufficient": True}
    prof = sum(1 for f in folds if f["net_pnl"] > 0)
    mean_exp = round(sum(f["expectancy"] for f in folds) / len(folds), 2)
    return {"folds": folds, "n_folds": len(folds), "mean_expectancy": mean_exp,
            "pct_folds_profitable": round(100 * prof / len(folds), 1),
            "insufficient": False}


def robustness_verdict(wf: dict, mc: dict, ci: dict) -> dict:
    """Plain-English combine. Robust only when the edge survives all three checks.
    Honest: this reduces curve-fit risk, it does not guarantee future profit."""
    if wf.get("insufficient") or mc.get("insufficient") or ci.get("insufficient"):
        return {"robust": False,
                "reasons": ["Insufficient trades/windows to validate — widen the "
                            "lookback or loosen the preset."]}
    reasons = []
    ok = True
    if wf["pct_folds_profitable"] >= 60:
        reasons.append(f"{wf['pct_folds_profitable']}% of walk-forward windows profitable")
    else:
        ok = False
        reasons.append(f"only {wf['pct_folds_profitable']}% of windows profitable (<60%)")
    if ci["lo"] > 0:
        reasons.append(f"expectancy CI [{ci['lo']}, {ci['hi']}] excludes zero")
    else:
        ok = False
        reasons.append(f"expectancy CI [{ci['lo']}, {ci['hi']}] includes zero (edge may be noise)")
    reasons.append(f"p95 Monte-Carlo drawdown ₹{mc['p95']}")
    return {"robust": ok, "reasons": reasons}
