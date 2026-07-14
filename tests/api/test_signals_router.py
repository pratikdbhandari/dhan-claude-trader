from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderType,
                         RiskCheck, Side, SignalType)
from services.trade_controller import PendingOrder
from api.auth import require_user
from api.deps import get_dhan_client, get_journal, get_pending_store
from api.routers import signals
from api.state import PendingStore


def _app(store, dhan, journal):
    app = FastAPI()
    app.include_router(signals.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_pending_store] = lambda: store
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    app.dependency_overrides[get_journal] = lambda: journal
    return app


def _pending(allowed=True):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET,
                       qty=10, price=100.0, stop_loss=95.0, target=110.0)
    check = RiskCheck(allowed=allowed, reasons=[] if allowed else ["Max open positions"])
    return PendingOrder(order_request=req, risk_check=check)


def _consensus():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    return ConsensusSignal(instrument=instr, providers=[], consensus=SignalType.BUY,
                           avg_confidence=80, agreement_pct=100,
                           indicator_snapshot={"entry": 100.0, "stop_loss": 95.0,
                                              "target": 110.0})


def test_list_pending_returns_stored_signals(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.get("/signals/pending")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["pending_id"] == pid
    assert body[0]["symbol"] == "RELIANCE"
    assert body[0]["risk_check"]["allowed"] is True


def test_confirm_places_order_and_removes_entry(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=True), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post(f"/signals/{pid}/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(fake_dhan.bracket) == 1
    assert store.get(pid) is None


def test_confirm_unknown_id_returns_404_and_places_nothing(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post("/signals/does-not-exist/confirm")

    assert resp.status_code == 404
    assert fake_dhan.placed == []
    assert fake_dhan.bracket == []


def test_confirm_double_call_second_is_404(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=True), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    first = client.post(f"/signals/{pid}/confirm")
    second = client.post(f"/signals/{pid}/confirm")

    assert first.status_code == 200
    assert second.status_code == 404
    assert len(fake_dhan.bracket) == 1


def test_confirm_risk_blocked_returns_blocked_status_and_places_nothing(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=False), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post(f"/signals/{pid}/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "BLOCKED"
    assert fake_dhan.placed == []
    assert fake_dhan.bracket == []


def test_pending_requires_auth(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    app = FastAPI()
    app.include_router(signals.router)
    app.dependency_overrides[get_pending_store] = lambda: store
    app.dependency_overrides[get_dhan_client] = lambda: fake_dhan
    app.dependency_overrides[get_journal] = lambda: temp_journal
    client = TestClient(app)

    resp = client.get("/signals/pending")

    assert resp.status_code == 401
