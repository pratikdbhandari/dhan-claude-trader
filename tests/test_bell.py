from datetime import date, datetime, timezone, timedelta

from services.bell import should_ring

IST = timezone(timedelta(hours=5, minutes=30))


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# 2026-07-14 is a Tuesday. Open 09:15. 09:05 -> 10 min to open.
def test_rings_inside_lead_window():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_rings_at_exact_lead_boundary():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_rings_one_minute_before_open():
    assert should_ring(_ist(2026, 7, 14, 9, 14), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_no_ring_before_lead_window():
    assert should_ring(_ist(2026, 7, 14, 8, 50), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_market_open():
    assert should_ring(_ist(2026, 7, 14, 10, 0), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_disabled():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=False, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_already_rung_today():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=date(2026, 7, 14)) is False


def test_rings_again_on_a_new_day():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=date(2026, 7, 13)) is True


def test_no_ring_on_weekend():
    assert should_ring(_ist(2026, 7, 18, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False
