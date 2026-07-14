from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_dhan_client
from api.routers import positions
from services.dhan_client import DhanError


def _app(dhan):
    app = FastAPI()
    app.include_router(positions.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    return app


def test_list_positions_returns_dhan_positions(fake_dhan):
    fake_dhan.positions = [{"tradingSymbol": "RELIANCE", "netQty": 10}]
    client = TestClient(_app(fake_dhan))

    resp = client.get("/positions")

    assert resp.status_code == 200
    assert resp.json() == [{"tradingSymbol": "RELIANCE", "netQty": 10}]


def test_list_positions_returns_502_on_dhan_error(fake_dhan, monkeypatch):
    def raise_error():
        raise DhanError("boom")
    fake_dhan.get_positions = raise_error
    client = TestClient(_app(fake_dhan))

    resp = client.get("/positions")

    assert resp.status_code == 502


def test_exit_position_calls_dhan_exit(fake_dhan):
    client = TestClient(_app(fake_dhan))

    resp = client.post("/positions/1/exit",
                       params={"exchange_segment": "NSE_EQ", "symbol": "RELIANCE"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dhan_order_id"] == "PAPER-EXIT-RELIANCE"


def test_positions_requires_auth(fake_dhan):
    app = FastAPI()
    app.include_router(positions.router)
    app.dependency_overrides[get_dhan_client] = lambda: fake_dhan
    client = TestClient(app)

    resp = client.get("/positions")

    assert resp.status_code == 401
