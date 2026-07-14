import numpy as np
import pandas as pd

from services.backtest_robust import walk_forward, robustness_verdict


def _trending_df(n=1400):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 120, n) + rng.normal(0, 1.0, n)
    high = close + 1.0
    low = close - 1.0
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


_SIM_KW = {"active_ids": list(range(1, 30)), "style": "intraday",
           "segment": "equity_intraday", "warmup": 200}


def test_walk_forward_returns_folds_and_aggregate():
    wf = walk_forward(_trending_df(), n_splits=3, sim_kwargs=_SIM_KW)
    assert wf["n_folds"] >= 1
    assert 0 <= wf["pct_folds_profitable"] <= 100
    for f in wf["folds"]:
        for k in ("net_pnl", "win_rate", "expectancy", "profit_factor",
                  "max_drawdown", "n_trades"):
            assert k in f


def test_walk_forward_insufficient_on_short_df():
    wf = walk_forward(_trending_df(n=210), n_splits=4, min_test=200,
                      sim_kwargs=_SIM_KW)
    assert wf["insufficient"] is True


def test_robustness_verdict_robust_when_all_pass():
    wf = {"pct_folds_profitable": 75.0, "insufficient": False}
    mc = {"p95": 1200.0, "insufficient": False}
    ci = {"lo": 15.0, "hi": 60.0, "insufficient": False}
    v = robustness_verdict(wf, mc, ci)
    assert v["robust"] is True
    assert v["reasons"]


def test_robustness_verdict_not_robust_when_ci_includes_zero():
    wf = {"pct_folds_profitable": 75.0, "insufficient": False}
    mc = {"p95": 1200.0, "insufficient": False}
    ci = {"lo": -5.0, "hi": 60.0, "insufficient": False}
    assert robustness_verdict(wf, mc, ci)["robust"] is False


def test_robustness_verdict_not_robust_when_insufficient():
    wf = {"pct_folds_profitable": 0.0, "insufficient": True}
    mc = {"p95": 0.0, "insufficient": True}
    ci = {"lo": 0.0, "hi": 0.0, "insufficient": True}
    assert robustness_verdict(wf, mc, ci)["robust"] is False
