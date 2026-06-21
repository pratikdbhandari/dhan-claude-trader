from services.quality_gate import (fundamental_gate, news_gate, quality_score,
                                   apply_gate, GateResult)
from core.models import ConsensusSignal, Instrument, SignalType


def _consensus(net=0.4, agree=75, side=SignalType.BUY):
    return ConsensusSignal(
        instrument=Instrument(symbol="X", exchange_segment="NSE_EQ", security_id="1",
                              kind="EQUITY"),
        providers=[], consensus=side, avg_confidence=70, agreement_pct=agree,
        indicator_snapshot={"net_score": net})


def test_fundamental_gate_vetoes_long_on_bad_pe():
    ok, reasons = fundamental_gate({"pe": -5}, "BUY", "EQUITY")
    assert ok is False and reasons


def test_fundamental_gate_passes_non_equity():
    assert fundamental_gate({}, "BUY", "INDEX") == (True, [])


def test_news_gate_vetoes_on_results():
    ok, msgs = news_gate(["RESULTS"])
    assert ok is False


def test_news_gate_cautions_on_expiry():
    ok, msgs = news_gate(["EXPIRY"])
    assert ok is True and any("expiry" in m for m in msgs)


def test_quality_score_higher_with_strength_and_agreement():
    strong = quality_score(0.5, 100, True, True, False)
    weak = quality_score(0.16, 30, True, True, False)
    assert strong > weak
    assert 0 <= strong <= 100


def test_apply_gate_passes_clean_strong_signal():
    g = apply_gate(_consensus(net=0.5, agree=100), {"pe": 25}, [], kind="EQUITY")
    assert isinstance(g, GateResult)
    assert g.passed is True and g.vetoed is False
    assert g.score >= 50


def test_apply_gate_blocks_on_results_event():
    g = apply_gate(_consensus(net=0.5, agree=100), {"pe": 25}, ["RESULTS"],
                   kind="EQUITY")
    assert g.passed is False and g.vetoed is True


def test_apply_gate_blocks_weak_signal_below_threshold():
    g = apply_gate(_consensus(net=0.16, agree=20), {"pe": 25}, [], kind="EQUITY")
    assert g.passed is False and g.vetoed is False   # not vetoed, just low score
