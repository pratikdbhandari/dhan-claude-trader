import services.strategies.volume  # noqa: F401 - registers strategies
import services.strategies.structure  # noqa: F401 - registers strategies
from services.strategies import base
from core.models import SignalType


def test_all_registered():
    assert all(i in base.REGISTRY for i in range(24, 30))


def test_votes_valid(trending_candles):
    for i in range(24, 30):
        v = base.REGISTRY[i].run(trending_candles)
        assert v.vote in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
        assert 0 <= v.strength <= 100
