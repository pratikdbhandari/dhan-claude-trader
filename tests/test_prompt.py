from services.prompt import build_prompt
from core.models import ConfluenceSnapshot, Regime, SignalType, StrategyVote


def _snap():
    v = StrategyVote(1, "ema_cross", "trend", SignalType.BUY, 70, "x")
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[v],
                              category_scores={"trend": 0.7}, net_score=0.35,
                              bias=SignalType.BUY, buy_count=1, sell_count=0, hold_count=0)


def test_prompt_contains_all_sections():
    p = build_prompt(symbol="NIFTY", snapshot=_snap(), last_price=22000,
                     indicators={"rsi": 61.2}, news=["RBI holds rate"],
                     fundamentals={"pe": 25.3}, position="none")
    for token in ["NIFTY", "TRENDING", "ema_cross", "RBI holds rate", "25.3",
                  "22000", "JSON", "signal"]:
        assert token in p


def test_prompt_handles_empty_context():
    p = build_prompt(symbol="X", snapshot=_snap(), last_price=100,
                     indicators={}, news=[], fundamentals={}, position="none")
    assert "X" in p and "JSON" in p
