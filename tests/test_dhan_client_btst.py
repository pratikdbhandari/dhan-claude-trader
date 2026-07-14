from core.models import Instrument, OrderRequest, OrderType, Side, TradeMode
from services.dhan_client import DhanClient


class FakeSdk:
    def __init__(self):
        self.calls = []

    def place_order(self, **kwargs):
        self.calls.append(kwargs)
        return {"data": {"orderId": "O123"}}


def _req(product_type="CNC"):
    return OrderRequest(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        side=Side.BUY, order_type=OrderType.MARKET, qty=5, price=100.0,
        product_type=product_type)


def test_paper_place_order_reports_product_agnostic_success():
    c = DhanClient(sdk=object(), mode=TradeMode.PAPER)
    res = c.place_order(_req("CNC"))
    assert res.ok and res.status == "PLACED"


def test_live_place_order_forwards_cnc_product_type():
    sdk = FakeSdk()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    c.place_order(_req("CNC"))
    assert sdk.calls[0]["product_type"] == "CNC"


def test_live_place_order_defaults_intraday_when_unset():
    sdk = FakeSdk()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    c.place_order(_req("INTRADAY"))
    assert sdk.calls[0]["product_type"] == "INTRADAY"
