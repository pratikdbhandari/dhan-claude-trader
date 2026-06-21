import pytest
from services.dhan_client import DhanClient, DhanError
from core.models import Instrument, TradeMode, OrderResult

class DataSDK:
    def ticker_data(self, securities):
        return {"status": "success",
                "data": {"data": {"NSE_EQ": {"2885": {"last_price": 2500.5}}}}}

def _instr():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                      security_id="2885", kind="EQUITY")

def test_get_ltp_parses_last_price():
    c = DhanClient(sdk=DataSDK(), mode=TradeMode.PAPER)
    assert c.get_ltp(_instr()) == 2500.5

def test_get_ltp_error_surfaced():
    class Boom:
        def ticker_data(self, securities): raise RuntimeError("net down")
    c = DhanClient(sdk=Boom(), mode=TradeMode.PAPER)
    with pytest.raises(DhanError):
        c.get_ltp(_instr())
