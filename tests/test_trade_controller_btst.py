from core.models import Instrument, OrderResult, OrderType, TradeMode, Side
from core.models import BtstCandidate
from services.risk_manager import RiskConfig
from services.trade_controller import prepare_btst_order, confirm_and_place
from data.journal import init_db, list_trades


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        raise AssertionError("BTST must not use bracket orders")


def _cand():
    return BtstCandidate(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        entry=100.0, target=103.0, stop=98.0, net_score=0.4, close_strength=0.9,
        volume_ratio=1.5, reasons=["strong close"], gap_risk="gap risk")


def test_prepare_btst_builds_cnc_request_and_runs_gate():
    pending = prepare_btst_order(_cand(), equity=100000, cfg=RiskConfig(),
                                 day_pnl_value=0, open_count=0)
    req = pending.order_request
    assert req.product_type == "CNC"
    assert req.order_type is OrderType.MARKET
    assert req.side is Side.BUY
    assert req.stop_loss is None and req.target is None
    assert req.qty > 0
    assert pending.risk_check.allowed is True


def test_prepare_btst_blocks_when_max_positions_reached():
    pending = prepare_btst_order(_cand(), equity=100000,
                                 cfg=RiskConfig(max_open_positions=2),
                                 day_pnl_value=0, open_count=2)
    assert pending.risk_check.allowed is False


def test_confirm_places_plain_cnc_order_not_bracket(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = prepare_btst_order(_cand(), equity=100000, cfg=RiskConfig(),
                                 day_pnl_value=0, open_count=0)
    res = confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.ok
    assert len(dhan.placed) == 1
    assert dhan.placed[0].product_type == "CNC"
    assert len(list_trades(conn)) == 1
