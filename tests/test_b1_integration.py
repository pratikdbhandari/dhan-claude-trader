"""B1 end-to-end: log orders -> to_legs -> accounting realized P&L."""
import pytest
from data.journal import init_db, log_order, to_legs
from services.accounting import realized_trades
from core.models import (Instrument, OrderRequest, OrderResult, Side, OrderType,
                         TradeMode)

def _req(side, qty, price):
    return OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ",
                        security_id="1", kind="EQUITY"),
                        side=side, order_type=OrderType.MARKET, qty=qty, price=price)

def test_journal_to_accounting_roundtrip(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _req(Side.BUY, 10, 100),
              OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED", exec_price=100))
    log_order(conn, _req(Side.SELL, 10, 110),
              OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED", exec_price=110))
    legs = to_legs(conn, mode="PAPER")
    assert len(legs) == 2
    realized = realized_trades(legs, mode="PAPER")
    assert len(realized) == 1
    assert realized[0].gross_pnl == 100.0
    assert realized[0].net_pnl < 100.0
