"""Read-only live-connectivity self-test. Calls every live Dhan READ endpoint and
verifies our PARSERS handle the real response — WITHOUT placing/modifying/cancelling
any order. Run before the first real trade to catch response-shape mismatches.

Also holds the token pre-flight (token_status) — a network-free check answering
"will my access token survive the session I am about to trade?".

Pure-ish: run_checks takes an injected client + instruments so it is unit-testable
with a fake SDK. NEVER calls any write method."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


def _next_close(now: datetime) -> datetime:
    """End of the next session that could be traded from `now` — today's close if
    the market has not shut yet, otherwise the next trading day's."""
    from services.market_clock import CLOSE, IST, next_trading_day
    is_weekday = now.weekday() < 5
    day = (now.date() if (is_weekday and now.time() < CLOSE)
           else next_trading_day(now.date()))
    return datetime.combine(day, CLOSE, tzinfo=IST)


def token_status(token: str | None, now: datetime | None = None) -> dict:
    """Will the Dhan access token outlive the next session? No network.

    Dhan tokens are short-lived and die silently mid-session — every data call
    then fails while the UI keeps rendering the last snapshot. Checking the JWT's
    own `exp` up front turns that into a warning you can act on before the open.

    The signature is NOT verified: we are not the issuer and are not
    authenticating anything here, only reading the expiry Dhan itself stamped.

    state: OK | SOON | EXPIRED | UNKNOWN  (SOON = dies before the next close)
    """
    import jwt
    from services.market_clock import IST

    now = now or datetime.now(IST)
    if not token:
        return {"state": "UNKNOWN", "expires_at": None, "hours_left": None,
                "detail": "No Dhan access token saved."}
    try:
        exp = jwt.decode(token, options={"verify_signature": False})["exp"]
        expires = datetime.fromtimestamp(int(exp), IST)
    except Exception:                              # noqa: BLE001 - any bad token
        return {"state": "UNKNOWN", "expires_at": None, "hours_left": None,
                "detail": "Dhan token unreadable — paste it again in Settings."}

    at = expires.strftime("%a %d %b %H:%M")
    left = (expires - now).total_seconds()
    hours = round(left / 3600, 1)
    if left <= 0:
        return {"state": "EXPIRED", "expires_at": at, "hours_left": 0.0,
                "detail": f"Dhan token EXPIRED {at}. Market data will not load "
                          f"until you paste a fresh token."}
    if expires < _next_close(now):
        return {"state": "SOON", "expires_at": at, "hours_left": hours,
                "detail": f"Dhan token expires {at} — before the next 15:30 close. "
                          f"Data will cut out mid-session. Refresh it before you trade."}
    return {"state": "OK", "expires_at": at, "hours_left": hours,
            "detail": f"Dhan token valid until {at} ({hours}h)."}


@dataclass
class Check:
    name: str
    status: str        # PASS | FAIL | SKIP
    detail: str


def _run(name: str, fn) -> Check:
    try:
        ok, detail = fn()
        return Check(name, "PASS" if ok else "FAIL", detail)
    except Exception as e:                     # noqa: BLE001
        return Check(name, "FAIL", f"{type(e).__name__}: {e}")


def run_checks(client, *, equity_instr, index_instr=None) -> list[Check]:
    checks: list[Check] = []

    def funds():
        f = client.get_fund_limits()
        bal = f.get("availabelBalance", f.get("availableBalance")) if isinstance(f, dict) else None
        return (bal is not None), f"balance={bal}"
    checks.append(_run("funds (get_fund_limits)", funds))

    def ltp():
        v = client.get_ltp(equity_instr)
        return (isinstance(v, (int, float)) and v > 0), f"{equity_instr.symbol} LTP={v}"
    checks.append(_run("LTP (ticker_data parse)", ltp))

    def candles_day():
        df = client.get_candles(equity_instr, interval="day", lookback_days=10)
        return (len(df) > 0), f"{len(df)} daily rows, cols={list(df.columns)[:5]}"
    checks.append(_run("candles daily (historical_daily_data)", candles_day))

    def candles_intra():
        df = client.get_candles(equity_instr, interval=15, lookback_days=3)
        return (len(df) >= 0), f"{len(df)} 15m rows"
    checks.append(_run("candles intraday (intraday_minute_data)", candles_intra))

    def positions():
        p = client.get_positions()
        return (isinstance(p, list)), f"{len(p) if isinstance(p, list) else '?'} positions"
    checks.append(_run("positions (get_positions)", positions))

    def holdings():
        h = client.get_holdings()
        return (isinstance(h, list)), f"{len(h) if isinstance(h, list) else '?'} holdings"
    checks.append(_run("holdings (get_holdings)", holdings))

    if index_instr is not None and index_instr.security_id:
        from services.options_chain import get_expiries, get_chain

        def expiries():
            ex = get_expiries(index_instr, client)
            return (len(ex) > 0), f"{len(ex)} expiries, first={ex[0] if ex else None}"
        checks.append(_run("option expiries (expiry_list)", expiries))

        def chain():
            ex = get_expiries(index_instr, client)
            if not ex:
                return False, "no expiries to fetch chain"
            ch = get_chain(index_instr, ex[0], client)
            has_greeks = bool(ch) and ch[0]["ce"].get("delta") is not None
            return (len(ch) > 0), f"{len(ch)} strikes, greeks={'yes' if has_greeks else 'no'}"
        checks.append(_run("option chain (option_chain parse)", chain))

    return checks


def verdict(checks: list[Check]) -> str:
    fails = [c for c in checks if c.status == "FAIL"]
    if not fails:
        return "ALL READ ENDPOINTS OK — safe to proceed to a tiny live order test."
    return (f"{len(fails)} endpoint(s) FAILED — fix the parser/shape before live trading: "
            + ", ".join(c.name for c in fails))
