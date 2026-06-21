from services.regime import classify_regime
from core.models import Regime

def test_trending_market_classified_trending(trending_candles):
    assert classify_regime(trending_candles) is Regime.TRENDING

def test_ranging_market_not_trending(ranging_candles):
    assert classify_regime(ranging_candles) in (Regime.RANGING, Regime.VOLATILE)
