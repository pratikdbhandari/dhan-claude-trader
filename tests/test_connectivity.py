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


# ---------------------------------------------------------------- token pre-flight
def _tok(expires_at):
    import jwt
    return jwt.encode({"exp": int(expires_at.timestamp()), "dhanClientId": "x"},
                      "irrelevant-we-never-verify", algorithm="HS256")


def test_token_status_ok_when_it_outlives_the_next_close():
    from datetime import datetime, timedelta
    from services.connectivity import token_status
    from services.market_clock import IST
    now = datetime(2026, 7, 17, 9, 0, tzinfo=IST)          # Fri, pre-open
    s = token_status(_tok(now + timedelta(days=20)), now=now)
    assert s["state"] == "OK" and s["hours_left"] > 400


def test_token_dying_midsession_tomorrow_is_flagged_soon():
    """The real 2026-07-16 blocker: checked late Thursday night, the token
    expires 09:21 Friday — after Thursday's close, so a naive 'expires today?'
    test calls it fine, but it dies 6 minutes into Friday's session."""
    from datetime import datetime
    from services.connectivity import token_status
    from services.market_clock import IST
    thu_night = datetime(2026, 7, 16, 23, 58, tzinfo=IST)
    fri_0921 = datetime(2026, 7, 17, 9, 21, tzinfo=IST)
    s = token_status(_tok(fri_0921), now=thu_night)
    assert s["state"] == "SOON"
    assert "before the next 15:30 close" in s["detail"]
    assert s["expires_at"] == "Fri 17 Jul 09:21"


def test_token_dying_before_todays_close_is_soon():
    from datetime import datetime
    from services.connectivity import token_status
    from services.market_clock import IST
    now = datetime(2026, 7, 17, 10, 0, tzinfo=IST)         # Fri, mid-session
    s = token_status(_tok(datetime(2026, 7, 17, 14, 0, tzinfo=IST)), now=now)
    assert s["state"] == "SOON"


def test_token_expired():
    from datetime import datetime
    from services.connectivity import token_status
    from services.market_clock import IST
    now = datetime(2026, 7, 17, 10, 0, tzinfo=IST)
    s = token_status(_tok(datetime(2026, 7, 17, 9, 30, tzinfo=IST)), now=now)
    assert s["state"] == "EXPIRED" and s["hours_left"] == 0.0
    assert "EXPIRED" in s["detail"]


def test_token_missing_or_garbage_is_unknown():
    from services.connectivity import token_status
    assert token_status(None)["state"] == "UNKNOWN"
    assert token_status("")["state"] == "UNKNOWN"
    assert token_status("not-a-jwt")["state"] == "UNKNOWN"
    assert token_status("aaa.bbb.ccc")["state"] == "UNKNOWN"


def test_token_status_never_verifies_signature():
    """Token is signed by Dhan with a secret we do not hold; reading exp must
    still work."""
    from datetime import datetime, timedelta
    from services.connectivity import token_status
    from services.market_clock import IST
    import jwt
    now = datetime(2026, 7, 17, 9, 0, tzinfo=IST)
    foreign = jwt.encode({"exp": int((now + timedelta(days=30)).timestamp())},
                         "dhans-secret-we-do-not-have", algorithm="HS256")
    assert token_status(foreign, now=now)["state"] == "OK"
