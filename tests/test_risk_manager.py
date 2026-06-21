from services.risk_manager import (RiskConfig, load_risk_config, position_size,
                                    pre_trade_check, day_pnl, open_position_count)
from core.models import (Instrument, OrderRequest, Side, OrderType, TradeMode)


def _req(qty=10, price=100.0, stop=98.0):
    return OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ",
                        security_id="1", kind="EQUITY"),
                        side=Side.BUY, order_type=OrderType.MARKET, qty=qty,
                        price=price, stop_loss=stop)


def test_load_config_defaults():
    cfg = load_risk_config({})
    assert cfg.max_daily_loss == 10000.0
    assert cfg.max_risk_per_trade_pct == 1.0
    assert cfg.max_open_positions == 2


def test_position_size_math():
    # equity 100000, 1% = 1000 risk, per-share 2 => 500 qty
    assert position_size(100000, 100, 98, 1.0) == 500


def test_position_size_zero_when_no_stop_distance():
    assert position_size(100000, 100, 100, 1.0) == 0


def test_check_allows_within_limits():
    cfg = RiskConfig()
    rc = pre_trade_check(_req(qty=10), cfg, equity=100000, day_pnl_value=-2000,
                         open_count=0)
    assert rc.allowed is True and rc.reasons == []
    assert rc.remaining_loss_buffer == 8000


def test_check_blocks_on_daily_loss():
    cfg = RiskConfig()
    rc = pre_trade_check(_req(), cfg, equity=100000, day_pnl_value=-10000, open_count=0)
    assert rc.allowed is False
    assert any("Daily loss" in r for r in rc.reasons)
    assert rc.remaining_loss_buffer == 0


def test_check_blocks_on_max_positions():
    cfg = RiskConfig()
    rc = pre_trade_check(_req(), cfg, equity=100000, day_pnl_value=0, open_count=2)
    assert rc.allowed is False
    assert any("Max open positions" in r for r in rc.reasons)


def test_check_blocks_on_trade_risk_over_1pct():
    cfg = RiskConfig()
    # qty 1000 * |100-98|=2 => 2000 risk > 1% of 100000 (1000)
    rc = pre_trade_check(_req(qty=1000), cfg, equity=100000, day_pnl_value=0,
                         open_count=0)
    assert rc.allowed is False
    assert any("Trade risk" in r for r in rc.reasons)


def test_check_collects_multiple_reasons():
    cfg = RiskConfig()
    rc = pre_trade_check(_req(qty=1000), cfg, equity=100000, day_pnl_value=-10000,
                         open_count=2)
    assert rc.allowed is False and len(rc.reasons) == 3


class FakeDhan:
    mode = TradeMode.LIVE

    def get_positions(self):
        return [{"netQty": 10, "realizedProfit": 500, "unrealizedProfit": -200},
                {"netQty": 0, "realizedProfit": 100, "unrealizedProfit": 0}]


def test_day_pnl_live_from_positions():
    assert day_pnl(TradeMode.LIVE, dhan_client=FakeDhan()) == 400.0


def test_open_position_count_live_excludes_flat():
    assert open_position_count(TradeMode.LIVE, dhan_client=FakeDhan()) == 1


def test_day_pnl_paper_from_legs():
    legs = [
        {"symbol": "X", "segment": "equity_delivery", "side": "BUY", "qty": 10,
         "price": 100, "mode": "PAPER", "timestamp": "t0", "rr_predicted": None},
        {"symbol": "X", "segment": "equity_delivery", "side": "SELL", "qty": 10,
         "price": 110, "mode": "PAPER", "timestamp": "t1", "rr_predicted": None},
    ]
    pnl = day_pnl(TradeMode.PAPER, legs=legs, ltp_fn=lambda s: None)
    assert 90 < pnl < 100   # ~97.67 net after charges
