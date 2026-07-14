from core.models import BacktestResult, BacktestTrade
from services.backtest_robust import monte_carlo_drawdown, bootstrap_ci


def _trade(net):
    return BacktestTrade(symbol="X", side="BUY", entry_idx=0, exit_idx=1,
                         entry_price=100.0, exit_price=100.0 + net, gross_pnl=net,
                         charges=0.0, net_pnl=net, exit_reason="TARGET",
                         regime="TRENDING", net_score=0.4)


def _result(nets):
    trades = [_trade(n) for n in nets]
    return BacktestResult(trades=trades, n_trades=len(trades), wins=0, win_rate=0.0,
                          gross_pnl=0.0, net_pnl=sum(nets), profit_factor=0.0,
                          expectancy=0.0, max_drawdown=0.0, calibration=[])


_NETS = [10, 10, 10, 10, 10, 10, 10, 10, 10, -50]


def test_monte_carlo_drawdown_reproducible_and_correct():
    r = _result(_NETS)
    a = monte_carlo_drawdown(r, n=500, seed=0)
    b = monte_carlo_drawdown(r, n=500, seed=0)
    assert a == b
    assert a["insufficient"] is False
    assert a["worst"] == 50.0 and a["p95"] == 50.0 and a["mean"] == 50.0


def test_monte_carlo_insufficient_under_10_trades():
    r = _result([10, -5, 10])
    out = monte_carlo_drawdown(r, n=100, seed=0)
    assert out["insufficient"] is True


def test_bootstrap_ci_reproducible_and_bounded():
    r = _result(_NETS)
    a = bootstrap_ci(r, n=500, seed=0)
    b = bootstrap_ci(r, n=500, seed=0)
    assert a == b
    assert a["insufficient"] is False
    assert a["lo"] <= a["mean"] <= a["hi"]
    assert -6 <= a["mean"] <= 14


def test_bootstrap_insufficient_under_10_trades():
    out = bootstrap_ci(_result([10, -5]), n=100, seed=0)
    assert out["insufficient"] is True
