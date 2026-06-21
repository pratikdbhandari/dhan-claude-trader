"""End-to-end Phase A: candles -> regime -> confluence snapshot."""
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.strategies.engine import build_confluence
from services.regime import classify_regime
from core.models import Regime, SignalType


def test_full_pipeline(trending_candles):
    regime = classify_regime(trending_candles)
    assert regime in Regime
    snap = build_confluence(trending_candles, regime=regime, style="positional",
                            active_ids=list(range(1, 30)))
    assert snap.votes, "expected at least one eligible strategy to vote"
    assert snap.bias in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert snap.buy_count + snap.sell_count + snap.hold_count == len(snap.votes)
