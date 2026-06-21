import pytest
from services.trade_controller import (prepare_order, confirm_and_place,
                                       build_order_request, PendingOrder)
from services.risk_manager import RiskConfig
from data.journal import init_db, list_trades
from core.models import (ConsensusSignal, Instrument, SignalType, TradeMode,
                         OrderResult, Side)


def _instr():
    return Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                      kind="INDEX")


def _consensus(bias=SignalType.BUY, entry=100.0, stop=98.0, target=104.0):
    return ConsensusSignal(instrument=_instr(), providers=[], consensus=bias,
                           avg_confidence=72, agreement_pct=75,
                           indicator_snapshot={"entry": entry, "stop_loss": stop,
                                               "target": target})


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []
        self.bracket = []

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        self.bracket.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="BO1", exec_price=req.price)


def test_prepare_builds_request_and_runs_gate():
    cfg = RiskConfig()
    pending = prepare_order(_consensus(), _instr(), equity=100000, cfg=cfg,
                            day_pnl_value=0, open_count=0)
    assert isinstance(pending, PendingOrder)
    assert pending.order_request.side is Side.BUY
    assert pending.order_request.qty > 0
    assert pending.risk_check.allowed is True


def test_prepare_does_not_place(tmp_path):
    # prepare alone must never touch the broker
    dhan = FakeDhan()
    prepare_order(_consensus(), _instr(), equity=100000, cfg=RiskConfig(),
                  day_pnl_value=0, open_count=0)
    assert dhan.placed == [] and dhan.bracket == []


def test_confirm_places_and_logs_when_allowed(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = prepare_order(_consensus(), _instr(), equity=100000, cfg=RiskConfig(),
                            day_pnl_value=0, open_count=0)
    res = confirm_and_place(pending, dhan_client=dhan, journal_conn=conn,
                            consensus=_consensus())
    assert res.ok and res.status == "FILLED"
    assert len(dhan.bracket) == 1          # has SL+target => bracket
    assert len(list_trades(conn)) == 1     # journaled


def test_confirm_blocks_and_places_nothing_when_risk_denied(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    # daily loss breached => risk check denies
    pending = prepare_order(_consensus(), _instr(), equity=100000, cfg=RiskConfig(),
                            day_pnl_value=-10000, open_count=0)
    assert pending.risk_check.allowed is False
    res = confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.ok is False and res.status == "BLOCKED"
    assert dhan.placed == [] and dhan.bracket == []
    assert list_trades(conn) == []         # nothing logged to broker/journal
