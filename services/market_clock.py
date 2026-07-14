"""IST-aware NSE market-time helpers. Pure and `now`-injectable so callers pass a
timezone-aware datetime (tests inject fixed times). IST is a fixed UTC+5:30 offset
(India has no DST). NSE cash session 09:15-15:30, Mon-Fri. Public holidays are NOT
modeled here (documented limitation - next_trading_day only skips weekends)."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

OPEN = time(9, 15)
CLOSE = time(15, 30)
NEAR_CLOSE_START = time(15, 0)


def _ist(now: datetime) -> datetime:
    return now.astimezone(IST)


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def is_market_open(now: datetime) -> bool:
    n = _ist(now)
    return _is_weekday(n.date()) and OPEN <= n.time() <= CLOSE


def is_near_close(now: datetime) -> bool:
    n = _ist(now)
    return _is_weekday(n.date()) and NEAR_CLOSE_START <= n.time() <= CLOSE


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while not _is_weekday(nxt):
        nxt += timedelta(days=1)
    return nxt


def minutes_to_open(now: datetime) -> int | None:
    """Whole minutes until the next 09:15 open; None if the market is open now."""
    n = _ist(now)
    if is_market_open(n):
        return None
    if _is_weekday(n.date()) and n.time() < OPEN:
        target = datetime.combine(n.date(), OPEN, tzinfo=IST)
    else:
        d = next_trading_day(n.date())
        target = datetime.combine(d, OPEN, tzinfo=IST)
    return int((target - n).total_seconds() // 60)
