"""Market-open warning bell — pure decision logic. Whether to ring the pre-open
alarm right now. The launcher's background thread owns the side effects (sound,
popup) and the last_rung_date state; this module only decides."""
from __future__ import annotations
from datetime import date, datetime

from services import market_clock


def should_ring(now: datetime, *, enabled: bool, lead_minutes: int,
                last_rung_date: date | None) -> bool:
    """True when the pre-open bell should fire at `now`.

    Rings when enabled, the market is not already open, we are within the
    [1, lead_minutes] pre-open window, and we have not already rung today."""
    if not enabled:
        return False
    m = market_clock.minutes_to_open(now)
    if m is None:                       # market already open
        return False
    if not (1 <= m <= lead_minutes):
        return False
    today = now.astimezone(market_clock.IST).date()
    return last_rung_date != today
