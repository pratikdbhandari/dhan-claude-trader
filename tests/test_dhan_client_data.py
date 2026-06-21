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

def _candle_payload(n=3):
    return {"status": "success", "data": {
        "open": [100.0+i for i in range(n)], "high": [101.0+i for i in range(n)],
        "low": [99.0+i for i in range(n)], "close": [100.5+i for i in range(n)],
        "volume": [1000+i for i in range(n)], "timestamp": [1700000000+i*60 for i in range(n)]}}

class CandleSDK:
    def __init__(self): self.calls = []
    def intraday_minute_data(self, security_id, exchange_segment, instrument_type,
                             from_date, to_date, interval=1):
        self.calls.append(("intra", interval)); return _candle_payload()
    def historical_daily_data(self, security_id, exchange_segment, instrument_type,
                              from_date, to_date, expiry_code=0):
        self.calls.append(("daily", None)); return _candle_payload()

def test_get_candles_5min_dataframe():
    sdk = CandleSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    df = c.get_candles(Instrument(symbol="X", exchange_segment="NSE_EQ",
                                  security_id="1", kind="EQUITY"),
                       interval=5, lookback_days=5)
    assert list(df.columns)[:5] == ["open","high","low","close","volume"]
    assert len(df) == 3
    assert sdk.calls[0] == ("intra", 5)

def test_get_candles_day_uses_daily():
    sdk = CandleSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    df = c.get_candles(Instrument(symbol="X", exchange_segment="NSE_EQ",
                                  security_id="1", kind="EQUITY"),
                       interval="day", lookback_days=30)
    assert sdk.calls[0][0] == "daily" and len(df) == 3

class ExitSDK:
    def __init__(self, net): self.net = net; self.placed = []
    def get_positions(self):
        return {"status": "success", "data": [
            {"securityId": "2885", "netQty": self.net, "exchangeSegment": "NSE_EQ"}]}
    def place_order(self, **kw):
        self.placed.append(kw); return {"status": "success", "data": {"orderId": "E1"}}

def _ri():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                      security_id="2885", kind="EQUITY")

def test_exit_long_fires_opposite_sell_live():
    c = DhanClient(sdk=ExitSDK(net=10), mode=TradeMode.LIVE)
    res = c.exit_position(_ri())
    assert res.ok and res.status == "PLACED"
    assert c.sdk.placed[0]["transaction_type"] == "SELL"
    assert c.sdk.placed[0]["quantity"] == 10

def test_exit_flat_is_noop():
    c = DhanClient(sdk=ExitSDK(net=0), mode=TradeMode.LIVE)
    res = c.exit_position(_ri())
    assert res.ok and res.status == "FLAT"
    assert c.sdk.placed == []

def test_exit_paper_does_not_call_sdk():
    sdk = ExitSDK(net=5)
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    res = c.exit_position(_ri())
    assert res.ok and res.mode is TradeMode.PAPER
    assert sdk.placed == []
