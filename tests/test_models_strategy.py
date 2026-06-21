from core.models import StrategyVote, Regime, SignalType


def test_strategy_vote_defaults():
    v = StrategyVote(strategy_id=1, name="ema_cross", category="trend",
                     vote=SignalType.BUY, strength=70)
    assert v.vote is SignalType.BUY
    assert v.strength == 70
    assert v.category == "trend"


def test_regime_enum_values():
    assert {r.value for r in Regime} == {"TRENDING", "RANGING", "VOLATILE"}
