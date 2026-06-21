import pytest
from services.accounting import realized_trades

def _leg(symbol, side, qty, price, ts, segment="futures", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_short_then_cover_is_profit_when_price_falls():
    legs = [_leg("NF", "SELL", 50, 200, "t0"), _leg("NF", "BUY", 50, 190, "t1")]
    out = realized_trades(legs, mode="PAPER")
    assert len(out) == 1
    r = out[0]
    assert r.qty == 50
    assert r.gross_pnl == 500.0
    assert r.net_pnl < r.gross_pnl
