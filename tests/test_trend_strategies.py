import services.strategies.trend  # noqa: F401 - registers strategies
from services.strategies import base
from core.models import SignalType


def test_all_trend_registered():
    assert all(i in base.REGISTRY for i in range(1, 10))


def test_ema_cross_buys_in_uptrend(trending_candles):
    vote = base.REGISTRY[1].run(trending_candles)
    assert vote.vote is SignalType.BUY


def test_price_above_200ema_regime(trending_candles):
    vote = base.REGISTRY[8].run(trending_candles)
    assert vote.vote is SignalType.BUY
