import services.strategies.breakout  # noqa: F401 - registers strategies
from services.strategies import base
from core.models import SignalType


def test_all_registered():
    assert all(i in base.REGISTRY for i in range(18, 24))


def test_donchian_breaks_up_in_trend(trending_candles):
    v = base.REGISTRY[19].run(trending_candles)
    assert v.vote in (SignalType.BUY, SignalType.HOLD)
