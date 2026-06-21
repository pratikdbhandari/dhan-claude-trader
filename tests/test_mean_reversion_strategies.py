import services.strategies.mean_reversion  # noqa: F401 - registers strategies
from services.strategies import base
from core.models import SignalType


def test_all_registered():
    assert all(i in base.REGISTRY for i in range(10, 18))


def test_rsi_returns_valid_vote(ranging_candles):
    v = base.REGISTRY[10].run(ranging_candles)
    assert v.vote in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert 0 <= v.strength <= 100
