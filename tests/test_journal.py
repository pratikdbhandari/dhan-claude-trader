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

from data.journal import stats

def _close_row(conn, pnl, rr_pred, rr_ach):
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, side, qty,
        pnl, rr_predicted, rr_achieved, exec_status)
        VALUES ('t','PAPER','X','BUY',1,?,?,?,'FILLED')""", (pnl, rr_pred, rr_ach))
    conn.commit()

def test_stats_win_rate_and_avg_rr(conn):
    _close_row(conn, 100, 2.0, 1.8)
    _close_row(conn, -50, 2.0, -1.0)
    s = stats(conn, mode="PAPER")
    assert s["trades"] == 2
    assert s["wins"] == 1
    assert s["win_rate"] == 50.0
    assert s["avg_rr_predicted"] == 2.0
    assert s["avg_rr_achieved"] == pytest.approx(0.4)

def test_stats_empty(conn):
    s = stats(conn, mode="PAPER")
    assert s["trades"] == 0 and s["win_rate"] == 0.0

from data.journal import to_legs

def test_to_legs_filled_only_with_segment(conn):
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, security_id,
        product_type, kind, side, order_type, qty, entry, exec_price, exec_status)
        VALUES ('2026-06-21T10:00','PAPER','X','1','INTRADAY','EQUITY','BUY','MARKET',
        10, 100, 101, 'PLACED')""")
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, side, qty,
        exec_status) VALUES ('t','PAPER','Y','BUY',5,'REJECTED')""")
    conn.commit()
    legs = to_legs(conn, mode="PAPER")
    assert len(legs) == 1
    leg = legs[0]
    assert leg["symbol"] == "X" and leg["segment"] == "equity_intraday"
    assert leg["price"] == 101 and leg["qty"] == 10 and leg["side"] == "BUY"
    assert leg["mode"] == "PAPER" and leg["timestamp"] == "2026-06-21T10:00"

def test_to_legs_price_falls_back_to_entry(conn):
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, security_id,
        product_type, kind, side, qty, entry, exec_price, exec_status)
        VALUES ('t','PAPER','Z','1','CNC','EQUITY','BUY',1, 200, NULL, 'FILLED')""")
    conn.commit()
    leg = to_legs(conn, mode="PAPER")[0]
    assert leg["price"] == 200 and leg["segment"] == "equity_delivery"
