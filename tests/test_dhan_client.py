from services.dhan_client import DhanClient
from core.models import Instrument, OrderRequest, Side, OrderType, TradeMode


class FakeSDK:
    def __init__(self):
        self.placed = []

    def get_order_list(self):
        return {"status": "success", "data": []}

    def place_order(self, **kw):
        self.placed.append(kw)
        return {"status": "success", "data": {"orderId": "X1"}}


def _instr():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="2885")


def test_paper_mode_does_not_call_sdk():
    sdk = FakeSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok and res.mode is TradeMode.PAPER
    assert res.status == "PLACED"
    assert sdk.placed == []


def test_live_mode_calls_sdk():
    sdk = FakeSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok and res.dhan_order_id == "X1"
    assert len(sdk.placed) == 1


def test_error_is_surfaced_not_raised():
    class BoomSDK(FakeSDK):
        def place_order(self, **kw):
            raise RuntimeError("boom")
    c = DhanClient(sdk=BoomSDK(), mode=TradeMode.LIVE)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok is False and "boom" in res.error_message
