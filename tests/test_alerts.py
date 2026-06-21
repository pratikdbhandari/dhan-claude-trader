from services.alerts import signal_alerts, risk_alerts, collect, CRITICAL, INFO
from core.models import ConsensusSignal, Instrument, SignalType, RiskCheck


def _cs(sym, side, agree=80):
    return ConsensusSignal(
        instrument=Instrument(symbol=sym, exchange_segment="NSE_EQ", security_id="1"),
        providers=[], consensus=side, avg_confidence=70, agreement_pct=agree,
        indicator_snapshot={})


def test_signal_alerts_only_for_non_hold_high_agreement():
    al = signal_alerts([_cs("A", SignalType.BUY, 80),
                        _cs("B", SignalType.HOLD, 90),
                        _cs("C", SignalType.SELL, 40)])
    msgs = [a.message for a in al]
    assert len(al) == 1 and "A: BUY" in msgs[0]


def test_risk_alerts_on_block():
    rc = RiskCheck(allowed=False, reasons=["Daily loss limit reached"])
    al = risk_alerts(rc)
    assert al and al[0].level == CRITICAL


def test_collect_dedupes_with_seen():
    seen = set()
    first = collect([_cs("A", SignalType.BUY, 80)], seen=seen)
    assert len(first) == 1
    # same signal again => no fresh alert
    second = collect([_cs("A", SignalType.BUY, 80)], seen=seen)
    assert second == []
