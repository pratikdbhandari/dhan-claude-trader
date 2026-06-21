from services.strategies import base
from core.models import SignalType, StrategyVote

def test_register_and_run():
    base.REGISTRY.clear()

    @base.strategy(id=999, name="always_buy", category="trend",
                   regimes=("TRENDING",), intraday_only=False)
    def always_buy(df):
        return SignalType.BUY, 80, "test"

    assert 999 in base.REGISTRY
    spec = base.REGISTRY[999]
    vote = spec.run(df=None)
    assert isinstance(vote, StrategyVote)
    assert vote.vote is SignalType.BUY and vote.strength == 80

def test_eligible_filters_by_regime_and_style():
    base.REGISTRY.clear()
    @base.strategy(id=1, name="t", category="trend", regimes=("TRENDING",), intraday_only=True)
    def t(df): return SignalType.HOLD, 0, ""
    @base.strategy(id=2, name="m", category="mean_reversion", regimes=("RANGING",), intraday_only=False)
    def m(df): return SignalType.HOLD, 0, ""

    elig = base.eligible(regime="TRENDING", style="positional")
    assert [s.id for s in elig] == []
    elig2 = base.eligible(regime="TRENDING", style="intraday")
    assert [s.id for s in elig2] == [1]
