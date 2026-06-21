import pytest
from services.accounting import pnl_statement

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_statement_all_period_closed_trade():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-21T09:30"),
            _leg("X", "SELL", 10, 110, "2026-06-21T15:00")]
    s = pnl_statement(legs, mode="PAPER", period="all", period_key=None,
                      ltp_fn=lambda sym: None)
    assert s.gross_realized == 100.0
    assert s.net_realized == pytest.approx(97.67, abs=0.01)
    assert s.unrealized == 0.0
    assert s.total_pnl == pytest.approx(97.67, abs=0.01)
    assert (s.brokerage + s.stt + s.exchange_sebi_stamp + s.gst) == \
        pytest.approx(s.gross_realized - s.net_realized, abs=0.02)

def test_statement_includes_unrealized_open_position():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-21T09:30")]
    s = pnl_statement(legs, mode="PAPER", period="all", period_key=None,
                      ltp_fn=lambda sym: 110.0)
    assert s.gross_realized == 0.0
    assert s.unrealized == 100.0
    assert s.total_pnl == pytest.approx(s.net_realized + 100.0, abs=0.01)

def test_period_day_filter():
    legs = [_leg("X", "BUY", 10, 100, "2026-06-20T09:30"),
            _leg("X", "SELL", 10, 110, "2026-06-21T15:00")]
    s = pnl_statement(legs, mode="PAPER", period="day", period_key="2026-06-21",
                      ltp_fn=lambda sym: None)
    assert s.gross_realized == 0.0
