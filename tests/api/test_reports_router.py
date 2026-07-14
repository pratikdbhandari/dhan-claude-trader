from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_journal
from api.routers import reports
from data.journal import log_order
from core.models import (Instrument, OrderRequest, OrderResult, OrderType, Side,
                         TradeMode)


def _app(journal):
    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_journal] = lambda: journal
    return app


def test_get_pnl_returns_statement_shape(temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET, qty=10,
                       price=100.0)
    result = OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
                         dhan_order_id="O1", exec_price=100.0)
    log_order(temp_journal, req, result)
    client = TestClient(_app(temp_journal))

    resp = client.get("/reports/pnl", params={"mode": "PAPER", "period": "all"})

    assert resp.status_code == 200
    body = resp.json()
    assert "total_pnl" in body
    assert body["mode"] == "PAPER"


def test_get_eod_returns_report_dict(temp_journal):
    client = TestClient(_app(temp_journal))

    resp = client.get("/reports/eod", params={"mode": "PAPER"})

    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body


def test_reports_require_auth(temp_journal):
    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[get_journal] = lambda: temp_journal
    client = TestClient(app)

    resp = client.get("/reports/pnl")

    assert resp.status_code == 401
