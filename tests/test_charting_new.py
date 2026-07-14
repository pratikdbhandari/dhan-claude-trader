import plotly.graph_objects as go

from core.models import RealizedTrade
from services import charting


def _rt(net, closed):
    return RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
                         buy_price=100.0, sell_price=100.0 + net, gross_pnl=net,
                         charges=0.0, net_pnl=net, rr_predicted=None, rr_achieved=None,
                         opened_at="2026-07-01T09:00:00", closed_at=closed)


def test_equity_curve_returns_figure_and_cumulates():
    trades = [_rt(100, "2026-07-01T15:00:00"), _rt(-40, "2026-07-02T15:00:00"),
              _rt(60, "2026-07-03T15:00:00")]
    fig = charting.equity_curve(trades, colors=None)
    assert isinstance(fig, go.Figure)
    ys = list(fig.data[0].y)
    assert ys == [100, 60, 120]


def test_equity_curve_empty_returns_figure():
    fig = charting.equity_curve([], colors=None)
    assert isinstance(fig, go.Figure)


def test_provider_accuracy_bar_per_provider():
    rows = [{"provider": "claude", "calls": 10, "correct": 7, "accuracy": 70.0},
            {"provider": "groq", "calls": 8, "correct": 3, "accuracy": 37.5}]
    fig = charting.provider_accuracy(rows, colors=None)
    assert isinstance(fig, go.Figure)
    assert list(fig.data[0].x) == [70.0, 37.5] or list(fig.data[0].y) == [70.0, 37.5]


def test_provider_accuracy_empty_returns_figure():
    assert isinstance(charting.provider_accuracy([], colors=None), go.Figure)


def test_payoff_returns_figure_with_breakevens():
    xs = [90, 95, 100, 105, 110]
    ys = [-50, 0, 50, 0, -50]
    fig = charting.payoff(xs, ys, breakevens=[95, 105], colors=None)
    assert isinstance(fig, go.Figure)
