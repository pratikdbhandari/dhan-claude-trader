from services.options_strategy import build_credit_spread, SpreadPlan
from core.models import ConsensusSignal, Instrument, SignalType


def _consensus(side):
    return ConsensusSignal(
        instrument=Instrument(symbol="NIFTY", exchange_segment="IDX_I",
                              security_id="13", kind="INDEX"),
        providers=[], consensus=side, avg_confidence=70, agreement_pct=80,
        indicator_snapshot={})


def _chain():
    # strikes around 22000 spot, with deltas + premiums
    return [
        {"strike": 21800, "ce": {"ltp": 260, "delta": 0.70}, "pe": {"ltp": 40, "delta": -0.25}},
        {"strike": 21900, "ce": {"ltp": 190, "delta": 0.60}, "pe": {"ltp": 60, "delta": -0.32}},
        {"strike": 22000, "ce": {"ltp": 130, "delta": 0.50}, "pe": {"ltp": 100, "delta": -0.45}},
        {"strike": 22100, "ce": {"ltp": 85, "delta": 0.35}, "pe": {"ltp": 150, "delta": -0.60}},
        {"strike": 22200, "ce": {"ltp": 50, "delta": 0.25}, "pe": {"ltp": 220, "delta": -0.72}},
    ]


def test_bull_put_on_buy_consensus():
    plan = build_credit_spread(_consensus(SignalType.BUY), _chain(), spot=22000,
                               lot_size=50, sell_delta=0.30)
    assert isinstance(plan, SpreadPlan)
    assert plan.name == "bull_put"
    # sell put ~0.32 delta = 21900; hedge one strike lower OTM = 21800
    assert plan.sell_strike == 21900 and plan.buy_strike == 21800
    assert plan.credit > 0
    assert plan.max_loss < 0 < plan.max_profit


def test_bear_call_on_sell_consensus():
    plan = build_credit_spread(_consensus(SignalType.SELL), _chain(), spot=22000,
                               lot_size=50, sell_delta=0.30)
    assert plan.name == "bear_call"
    # sell call ~0.35 delta = 22100; hedge one strike higher = 22200
    assert plan.sell_strike == 22100 and plan.buy_strike == 22200
    assert plan.credit > 0


def test_hold_returns_none():
    assert build_credit_spread(_consensus(SignalType.HOLD), _chain(), 22000, 50) is None


def test_empty_chain_returns_none():
    assert build_credit_spread(_consensus(SignalType.BUY), [], 22000, 50) is None
