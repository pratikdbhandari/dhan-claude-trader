from fastapi.testclient import TestClient
from web.server import create_web_app
import web.deps as wdeps
from data.journal import log_order
from core.models import Instrument, OrderRequest, OrderResult, OrderType, Side, TradeMode


def _client(monkeypatch, temp_journal):
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_reports_renders_pnl_and_sections(monkeypatch, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET, qty=10, price=100.0)
    log_order(temp_journal, req, OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
              dhan_order_id="O1", exec_price=100.0))
    c = _client(monkeypatch, temp_journal)
    r = c.get("/reports")
    assert r.status_code == 200
    assert "Equity curve" in r.text
    assert "AI cost" in r.text
    assert "Audit ledger" in r.text
