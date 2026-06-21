import pytest
from services.charges import compute
from core.models import ChargeBreakdown

def test_delivery_buy_worked_example():
    c = compute("equity_delivery", "BUY", qty=10, price=100, mode="PAPER")
    assert isinstance(c, ChargeBreakdown)
    assert c.brokerage == 0
    assert c.stt == 1.00
    assert c.stamp == 0.15
    assert c.exchange_txn == 0.03
    assert c.total == 1.19

def test_delivery_sell_has_no_stamp():
    c = compute("equity_delivery", "SELL", qty=10, price=110, mode="PAPER")
    assert c.stamp == 0.0
    assert c.stt == 1.10
    assert c.total == 1.14

def test_options_sell_flat_brokerage():
    c = compute("options", "SELL", qty=50, price=200, mode="LIVE")
    assert c.brokerage == 20.0
    assert c.stt == 10.0
    assert c.total == pytest.approx(37.74, abs=0.01)

def test_intraday_brokerage_is_lower_of_flat_or_pct():
    c = compute("equity_intraday", "BUY", qty=1, price=100, mode="PAPER")
    assert c.brokerage == 0.03
