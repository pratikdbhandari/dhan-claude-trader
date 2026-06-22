from services.connectivity import run_checks, verdict, Check
from core.models import Instrument, TradeMode
import pandas as pd


class GoodSDK:
    def get_fund_limits(self):
        return {"data": {"availabelBalance": 50000}}

    def ticker_data(self, securities):
        return {"data": {"data": {"NSE_EQ": {"2885": {"last_price": 2500.0}}}}}

    def historical_daily_data(self, *a, **k):
        return {"data": {"open": [1, 2], "high": [1, 2], "low": [1, 2],
                         "close": [1, 2], "volume": [1, 2]}}

    def intraday_minute_data(self, *a, **k):
        return {"data": {"open": [1], "high": [1], "low": [1], "close": [1],
                         "volume": [1]}}

    def get_positions(self):
        return {"data": []}

    def get_holdings(self):
        return {"data": []}


def _Client(sdk):
    from services.dhan_client import DhanClient
    return DhanClient(sdk=sdk, mode=TradeMode.PAPER)


def _eq():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                      security_id="2885", kind="EQUITY")


def test_all_pass_with_good_sdk():
    checks = run_checks(_Client(GoodSDK()), equity_instr=_eq())
    assert all(isinstance(c, Check) for c in checks)
    statuses = {c.name: c.status for c in checks}
    assert all(s == "PASS" for s in statuses.values()), statuses
    assert "OK" in verdict(checks)


def test_failure_is_reported_not_raised():
    class BadSDK(GoodSDK):
        def ticker_data(self, securities):
            raise RuntimeError("403 unauthorized")
    checks = run_checks(_Client(BadSDK()), equity_instr=_eq())
    ltp = next(c for c in checks if "LTP" in c.name)
    assert ltp.status == "FAIL" and "403" in ltp.detail
    assert "FAILED" in verdict(checks)
