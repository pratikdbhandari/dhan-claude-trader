import numpy as np
import pandas as pd
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.backtest import score_strategies, prune_candidates


def _candles(n=400):
    close = 100 + np.cumsum(np.random.default_rng(11).normal(0.03, 1.0, n))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)})


def test_score_strategies_returns_all_with_names():
    scored = score_strategies(_candles(), style="positional",
                              segment="equity_delivery", warmup=150, time_cap=15)
    assert len(scored) == 29
    assert all("name" in r and "oos_exp" in r for r in scored)
    # ranked by oos_exp descending
    exps = [r["oos_exp"] for r in scored]
    assert exps == sorted(exps, reverse=True)


def test_prune_candidates_flags_negative_oos():
    fake = [{"id": 1, "name": "a", "oos_trades": 10, "oos_exp": -5.0},
            {"id": 2, "name": "b", "oos_trades": 10, "oos_exp": 3.0},
            {"id": 3, "name": "c", "oos_trades": 2, "oos_exp": -9.0}]  # too few trades
    out = prune_candidates(fake, min_trades=5)
    ids = [r["id"] for r in out]
    assert ids == [1]   # only #1: negative AND enough trades
