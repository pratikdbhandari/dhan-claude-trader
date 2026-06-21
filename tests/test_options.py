from services.options_payoff import payoff_curve, metrics
from services.options_chain import get_chain, get_expiries, nearest_by_delta


# ---------------- payoff math ----------------
def _bull_put_spread():
    # sell 100 put @5, buy 95 put @2, 1 lot of 50
    return [
        {"type": "PE", "action": "SELL", "strike": 100, "premium": 5, "lots": 1, "lot_size": 50},
        {"type": "PE", "action": "BUY", "strike": 95, "premium": 2, "lots": 1, "lot_size": 50},
    ]


def test_bull_put_spread_max_profit_is_net_credit():
    legs = _bull_put_spread()
    m = metrics(legs, spot_ref=100)
    # net credit = (5-2)*50 = 150 ; max loss = (width 5 - credit 3)*50 = 100
    assert m["max_profit"] == 150.0
    assert m["max_loss"] == -100.0
    assert m["breakevens"]   # one breakeven near 97


def test_long_call_payoff_sign():
    legs = [{"type": "CE", "action": "BUY", "strike": 100, "premium": 4,
             "lots": 1, "lot_size": 1}]
    xs, ys = payoff_curve(legs, 90, 110, step=10)
    # at spot 90 => loss = -4 ; at 110 => 110-100-4 = 6
    assert ys[0] == -4.0 and ys[-1] == 6.0


# ---------------- chain wrapper ----------------
class FakeSDK:
    def expiry_list(self, sid, seg):
        return {"data": ["2026-06-25", "2026-07-02"]}

    def option_chain(self, sid, seg, expiry):
        return {"data": {"oc": {
            "22000": {"ce": {"last_price": 120, "greeks": {"delta": 0.55}},
                      "pe": {"last_price": 90, "greeks": {"delta": -0.45}}},
            "22100": {"ce": {"last_price": 70, "greeks": {"delta": 0.32}},
                      "pe": {"last_price": 140, "greeks": {"delta": -0.62}}}}}}


class _Client:
    sdk = FakeSDK()


def _instr():
    from core.models import Instrument
    return Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                      kind="INDEX")


def test_get_expiries():
    assert get_expiries(_instr(), _Client()) == ["2026-06-25", "2026-07-02"]


def test_get_chain_parses_strikes():
    chain = get_chain(_instr(), "2026-06-25", _Client())
    assert [r["strike"] for r in chain] == [22000.0, 22100.0]
    assert chain[0]["ce"]["delta"] == 0.55


def test_nearest_by_delta_picks_closest():
    chain = get_chain(_instr(), "2026-06-25", _Client())
    row = nearest_by_delta(chain, "ce", 0.30)
    assert row["strike"] == 22100.0   # delta 0.32 closest to 0.30
