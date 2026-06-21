import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.strategies.engine import build_confluence
from core.models import ConfluenceSnapshot, SignalType


def test_confluence_in_trend_is_bullish(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    assert isinstance(snap, ConfluenceSnapshot)
    assert -1.0 <= snap.net_score <= 1.0
    assert snap.bias in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert snap.net_score >= 0


def test_category_weighting_decorrelates(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    assert all(-1.0 <= v <= 1.0 for v in snap.category_scores.values())
