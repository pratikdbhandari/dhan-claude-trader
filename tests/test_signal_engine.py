import pytest
from services.signal_engine import mock_signal, consensus, generate
from core.models import (ConfluenceSnapshot, Regime, SignalType, StrategyVote,
                         ProviderSignal, Instrument, ConsensusSignal)


def _snap(bias=SignalType.BUY, net=0.4):
    v = StrategyVote(1, "ema", "trend", bias, 70, "x")
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[v],
                              category_scores={"trend": net}, net_score=net,
                              bias=bias, buy_count=1, sell_count=0, hold_count=0)


def test_mock_signal_from_snapshot():
    sig = mock_signal(_snap(SignalType.BUY, 0.4), last_price=100.0, atr=2.0)
    assert sig.provider == "mock"
    assert sig.signal is SignalType.BUY
    assert sig.confidence == 40
    assert sig.entry == 100.0
    assert sig.stop_loss == 98.0 and sig.target == 104.0


def _ps(sig, conf):
    return ProviderSignal(provider="p", signal=sig, confidence=conf, entry=100,
                          stop_loss=98, target=104, risk_reward_ratio=2.0,
                          reasoning="r")


def test_consensus_majority_and_agreement():
    sigs = [_ps(SignalType.BUY, 80), _ps(SignalType.BUY, 70), _ps(SignalType.SELL, 60)]
    c = consensus(sigs)
    assert c["consensus"] is SignalType.BUY
    assert c["avg_confidence"] == 75
    assert c["agreement_pct"] == 67


def test_consensus_all_errored_is_hold():
    e = ProviderSignal(provider="p", signal=SignalType.HOLD, confidence=0, entry=None,
                       stop_loss=None, target=None, risk_reward_ratio=None,
                       reasoning="err", error=True)
    c = consensus([e])
    assert c["consensus"] is SignalType.HOLD and c["agreement_pct"] == 0


def _instr():
    return Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                      kind="INDEX")


def test_generate_mock_mode():
    cs = generate(_instr(), _snap(SignalType.BUY, 0.4), last_price=100, atr=2.0,
                  mode="mock")
    assert isinstance(cs, ConsensusSignal)
    assert cs.consensus is SignalType.BUY
    assert cs.providers[0].provider == "mock"


def test_generate_api_mode_with_fake_clients():
    specs = [{"name": "groq", "model": "m"}, {"name": "claude", "model": "m"}]

    def factory(spec):
        return lambda prompt: '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
    cs = generate(_instr(), _snap(SignalType.BUY, 0.4), last_price=100, atr=2.0,
                  mode="api", providers=specs, client_factory=factory)
    assert cs.consensus is SignalType.BUY
    assert len(cs.providers) == 2
    assert cs.agreement_pct == 100


def test_generate_caches_within_cooldown():
    cache = {}
    calls = {"n": 0}

    def factory(spec):
        def c(prompt):
            calls["n"] += 1
            return '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
        return c
    specs = [{"name": "groq", "model": "m"}]
    a = generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
                 client_factory=factory, cache=cache)
    b = generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
                 client_factory=factory, cache=cache)
    assert a is b
    assert calls["n"] == 1


def test_generate_force_bypasses_cache():
    cache = {}
    calls = {"n": 0}

    def factory(spec):
        def c(prompt):
            calls["n"] += 1
            return '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
        return c
    specs = [{"name": "groq", "model": "m"}]
    generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
             client_factory=factory, cache=cache)
    generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
             client_factory=factory, cache=cache, force=True)
    assert calls["n"] == 2
