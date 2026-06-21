import numpy as np
import pandas as pd
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.backtest import simulate, compare_exits


def _trend(n=300):
    close = 100 + np.linspace(0, 60, n) + np.random.default_rng(5).normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)})


def test_trailing_mode_produces_trail_exits():
    res = simulate(_trend(), active_ids=list(range(1, 30)), style="positional",
                   segment="equity_delivery", warmup=150, time_cap=40, trail_atr=2.0)
    reasons = {t.exit_reason for t in res.trades}
    # in a strong uptrend, trailing should produce TRAIL exits (or TIME)
    assert reasons.issubset({"TRAIL", "TIME"})
    assert "TARGET" not in reasons and "STOP" not in reasons  # no fixed exits in trail mode


def test_compare_exits_returns_both():
    out = compare_exits(_trend(), active_ids=list(range(1, 30)), style="positional",
                        segment="equity_delivery", warmup=150, time_cap=30,
                        trail_atr=2.0)
    assert "fixed" in out and "trailing" in out
    assert "in_sample" in out["fixed"] and "out_of_sample" in out["trailing"]


def test_fixed_mode_unchanged():
    # default (no trail) still yields fixed exit reasons only
    res = simulate(_trend(), active_ids=list(range(1, 30)), style="positional",
                   segment="equity_delivery", warmup=150, time_cap=30)
    reasons = {t.exit_reason for t in res.trades}
    assert reasons.issubset({"STOP", "TARGET", "TIME"})
