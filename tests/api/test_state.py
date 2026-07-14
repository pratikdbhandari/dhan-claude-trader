from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderType,
                         RiskCheck, Side, SignalType)
from services.trade_controller import PendingOrder
from api.state import PendingStore


def _pending():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET,
                       qty=10, price=100.0, stop_loss=95.0, target=110.0)
    check = RiskCheck(allowed=True)
    return PendingOrder(order_request=req, risk_check=check)


def _consensus():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    return ConsensusSignal(instrument=instr, providers=[], consensus=SignalType.BUY,
                           avg_confidence=80, agreement_pct=100)


def test_add_then_get_returns_stored_entry():
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    stored = store.get(pid)
    assert stored is not None
    assert stored.pending_id == pid
    assert stored.pending.order_request.instrument.symbol == "RELIANCE"


def test_get_unknown_id_returns_none():
    store = PendingStore(ttl_seconds=300)
    assert store.get("does-not-exist") is None


def test_entry_expires_after_ttl():
    clock = {"t": 1000.0}
    store = PendingStore(ttl_seconds=10, clock=lambda: clock["t"])
    pid = store.add(_pending(), _consensus())
    clock["t"] += 11
    assert store.get(pid) is None


def test_pop_removes_entry_so_it_cannot_be_confirmed_twice():
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    first = store.pop(pid)
    second = store.pop(pid)
    assert first is not None
    assert second is None


def test_list_active_excludes_expired():
    clock = {"t": 1000.0}
    store = PendingStore(ttl_seconds=10, clock=lambda: clock["t"])
    pid_keep = store.add(_pending(), _consensus())
    clock["t"] += 5
    pid_expire = store.add(_pending(), _consensus())
    clock["t"] += 6
    ids = {s.pending_id for s in store.list_active()}
    assert pid_keep not in ids
    assert pid_expire in ids


def test_dedup_fingerprint_marks_and_checks():
    store = PendingStore(ttl_seconds=300)
    assert store.already_pushed("RELIANCE:BUY:100:95") is False
    store.mark_pushed("RELIANCE:BUY:100:95")
    assert store.already_pushed("RELIANCE:BUY:100:95") is True
