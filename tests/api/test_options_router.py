from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_dhan_client
from api.routers import options


def _app(dhan):
    app = FastAPI()
    app.include_router(options.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    return app


class ExpiryDhan:
    """Extends FakeDhan-shaped object with the sdk methods options_chain.py calls."""
    def __init__(self, mode="PAPER"):
        self.mode = mode

        class _Sdk:
            def expiry_list(self, security_id, exchange_segment):
                return {"data": ["2026-07-31", "2026-08-28"]}

            def option_chain(self, security_id, exchange_segment, expiry):
                return {"data": {"oc": {
                    "2500": {"ce": {"last_price": 12.5, "iv": 18.0,
                                    "greeks": {"delta": 0.5}, "oi": 1000},
                             "pe": {"last_price": 10.0, "iv": 19.0,
                                    "greeks": {"delta": -0.5}, "oi": 900}},
                }}}
        self.sdk = _Sdk()


def test_expiries_returns_list_from_dhan():
    client = TestClient(_app(ExpiryDhan()))

    resp = client.get("/options/expiries", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13"})

    assert resp.status_code == 200
    assert resp.json() == ["2026-07-31", "2026-08-28"]


def test_chain_returns_parsed_rows():
    client = TestClient(_app(ExpiryDhan()))

    resp = client.get("/options/chain", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13",
        "expiry": "2026-07-31"})

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["strike"] == 2500.0
    assert body[0]["ce"]["ltp"] == 12.5


def test_payoff_computes_curve_and_metrics():
    client = TestClient(_app(ExpiryDhan()))
    payload = {"legs": [{"type": "CE", "action": "BUY", "strike": 100.0,
                         "premium": 5.0, "lots": 1, "lot_size": 1}],
              "spot_ref": 100.0}

    resp = client.post("/options/payoff", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert "max_profit" in body
    assert "max_loss" in body
    assert len(body["xs"]) == len(body["ys"])


def test_options_require_auth():
    app = FastAPI()
    app.include_router(options.router)
    app.dependency_overrides[get_dhan_client] = lambda: ExpiryDhan()
    client = TestClient(app)

    resp = client.get("/options/expiries", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13"})

    assert resp.status_code == 401
