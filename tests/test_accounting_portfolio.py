from services.accounting import portfolio

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_open_holding_with_ltp():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "SELL", 4, 110, "t1")]
    hold = portfolio(legs, mode="PAPER", ltp_fn=lambda s: 120.0)
    assert len(hold) == 1
    h = hold[0]
    assert h.qty == 6 and h.avg_cost == 100.0 and h.invested == 600.0
    assert h.ltp == 120.0 and h.current_value == 720.0
    assert h.unrealized_pnl == 120.0

def test_missing_ltp_yields_none():
    legs = [_leg("X", "BUY", 10, 100, "t0")]
    h = portfolio(legs, mode="PAPER", ltp_fn=lambda s: None)[0]
    assert h.ltp is None and h.current_value is None and h.unrealized_pnl is None

def test_weighted_avg_cost_multi_lot():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "BUY", 10, 120, "t1")]
    h = portfolio(legs, mode="PAPER", ltp_fn=lambda s: None)[0]
    assert h.qty == 20 and h.avg_cost == 110.0
