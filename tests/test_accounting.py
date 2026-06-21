import pytest
from services.accounting import realized_trades

def _leg(symbol, side, qty, price, ts, segment="equity_delivery", mode="PAPER", rr=None):
    return {"symbol": symbol, "segment": segment, "side": side, "qty": qty,
            "price": price, "mode": mode, "timestamp": ts, "rr_predicted": rr}

def test_single_roundtrip_net_after_charges():
    legs = [_leg("X", "BUY", 10, 100, "t0"), _leg("X", "SELL", 10, 110, "t1")]
    out = realized_trades(legs, mode="PAPER")
    assert len(out) == 1
    r = out[0]
    assert r.gross_pnl == 100.0
    assert r.charges == pytest.approx(2.33, abs=0.01)
    assert r.net_pnl == pytest.approx(97.67, abs=0.01)

def test_fifo_multi_lot_matching():
    legs = [_leg("X", "BUY", 10, 100, "t0"),
            _leg("X", "BUY", 10, 105, "t1"),
            _leg("X", "SELL", 15, 110, "t2")]
    out = realized_trades(legs, mode="PAPER")
    assert len(out) == 2
    assert out[0].qty == 10 and out[0].buy_price == 100
    assert out[1].qty == 5 and out[1].buy_price == 105
    assert out[0].gross_pnl == 100.0
    assert out[1].gross_pnl == 25.0

def test_mode_isolation():
    legs = [_leg("X", "BUY", 10, 100, "t0", mode="PAPER"),
            _leg("X", "SELL", 10, 110, "t1", mode="LIVE")]
    assert realized_trades(legs, mode="PAPER") == []
    assert realized_trades(legs, mode="LIVE") == []
