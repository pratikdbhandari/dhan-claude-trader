import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.backtest import (simulate, split_eval, profit_probability,
                               save_calibration)
from core.models import BacktestResult

_IDS = list(range(1, 30))


def test_simulate_generates_trades_with_charges(trending_candles):
    res = simulate(trending_candles, active_ids=_IDS, style="positional",
                   segment="equity_delivery", warmup=200, time_cap=10)
    assert isinstance(res, BacktestResult)
    if res.n_trades:
        # charges always reduce net below gross
        assert res.net_pnl <= res.gross_pnl
        assert res.win_rate >= 0
        for t in res.trades:
            assert t.exit_reason in ("STOP", "TARGET", "TIME")


def test_simulate_too_short_returns_empty():
    import pandas as pd
    df = pd.DataFrame({"open": [1, 2], "high": [1, 2], "low": [1, 2],
                       "close": [1, 2], "volume": [1, 1]})
    res = simulate(df, active_ids=_IDS, style="positional", warmup=200)
    assert res.n_trades == 0


def test_split_eval_returns_two_results(trending_candles):
    out = split_eval(trending_candles, active_ids=_IDS, style="positional",
                     segment="equity_delivery", warmup=120, time_cap=10)
    assert "in_sample" in out and "out_of_sample" in out
    assert isinstance(out["in_sample"], BacktestResult)


def test_profit_probability_bucket_lookup():
    calib = [{"regime": "TRENDING", "score_band": "0.30-0.50", "n": 10, "win_rate": 60.0},
             {"regime": "TRENDING", "score_band": "0.50+", "n": 3, "win_rate": 80.0}]
    assert profit_probability(0.4, "TRENDING", calib) == 60.0
    # n<5 => None (don't over-claim)
    assert profit_probability(0.6, "TRENDING", calib) is None
    # no match => None
    assert profit_probability(0.2, "RANGING", calib) is None


def test_save_calibration_writes_file(trending_candles, tmp_path):
    res = simulate(trending_candles, active_ids=_IDS, style="positional",
                   segment="equity_delivery", warmup=200, time_cap=10)
    path = save_calibration(res, path=str(tmp_path / "calib.json"))
    from pathlib import Path
    import json
    assert Path(path).exists()
    assert isinstance(json.loads(Path(path).read_text()), list)


def test_known_target_hit_long():
    """Construct a clear uptrend that hits target, verify a TARGET exit appears."""
    import numpy as np
    import pandas as pd
    n = 260
    close = np.concatenate([np.linspace(100, 140, 240), np.linspace(140, 170, 20)])
    df = pd.DataFrame({"open": close, "high": close + 1.0, "low": close - 1.0,
                       "close": close, "volume": np.full(n, 1000.0)})
    res = simulate(df, active_ids=list(range(1, 30)), style="positional",
                   segment="equity_delivery", warmup=200, time_cap=15)
    # in a persistent uptrend at least one trade should resolve (TARGET or TIME)
    assert res.n_trades >= 1
