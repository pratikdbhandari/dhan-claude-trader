from datetime import date, datetime, timezone, timedelta

from services.market_clock import (is_market_open, is_near_close,
                                    minutes_to_open, next_trading_day)

IST = timezone(timedelta(hours=5, minutes=30))


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_near_close_true_inside_window():
    assert is_near_close(_ist(2026, 7, 14, 15, 0)) is True
    assert is_near_close(_ist(2026, 7, 14, 15, 30)) is True
    assert is_near_close(_ist(2026, 7, 14, 15, 15)) is True


def test_near_close_false_outside_window():
    assert is_near_close(_ist(2026, 7, 14, 14, 59)) is False
    assert is_near_close(_ist(2026, 7, 14, 15, 31)) is False


def test_near_close_false_on_weekend():
    assert is_near_close(_ist(2026, 7, 18, 15, 15)) is False


def test_market_open_window():
    assert is_market_open(_ist(2026, 7, 14, 9, 15)) is True
    assert is_market_open(_ist(2026, 7, 14, 15, 30)) is True
    assert is_market_open(_ist(2026, 7, 14, 9, 14)) is False
    assert is_market_open(_ist(2026, 7, 14, 15, 31)) is False
    assert is_market_open(_ist(2026, 7, 18, 12, 0)) is False


def test_minutes_to_open_before_open_same_day():
    assert minutes_to_open(_ist(2026, 7, 14, 9, 0)) == 15


def test_minutes_to_open_none_when_open():
    assert minutes_to_open(_ist(2026, 7, 14, 10, 0)) is None


def test_minutes_to_open_after_close_rolls_to_next_day():
    assert minutes_to_open(_ist(2026, 7, 14, 16, 0)) == 1035


def test_minutes_to_open_friday_evening_rolls_to_monday():
    assert minutes_to_open(_ist(2026, 7, 17, 18, 0)) == (2 * 24 * 60) + (15 * 60 + 15)


def test_next_trading_day_skips_weekend():
    assert next_trading_day(date(2026, 7, 17)) == date(2026, 7, 20)
    assert next_trading_day(date(2026, 7, 14)) == date(2026, 7, 15)
