import pytest
from data.journal import init_db, log_order, list_trades
from core.models import (Instrument, OrderRequest, OrderResult, Side, OrderType,
                         TradeMode)

@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "trades.db"))

def _req():
    return OrderRequest(instrument=Instrument(symbol="RELIANCE",
                        exchange_segment="NSE_EQ", security_id="2885", kind="EQUITY"),
                        side=Side.BUY, order_type=OrderType.MARKET, qty=10, price=2500.0)

def test_log_and_list_roundtrip(conn):
    res = OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                      dhan_order_id="P1", exec_price=2500.0)
    rid = log_order(conn, _req(), res)
    assert isinstance(rid, int)
    rows = list_trades(conn)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE"
    assert rows[0]["exec_status"] == "PLACED"
    assert rows[0]["mode"] == "PAPER"

def test_list_filters_by_mode(conn):
    log_order(conn, _req(), OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED"))
    log_order(conn, _req(), OrderResult(ok=True, mode=TradeMode.LIVE, status="PLACED"))
    assert len(list_trades(conn, mode="PAPER")) == 1
    assert len(list_trades(conn, mode="LIVE")) == 1
