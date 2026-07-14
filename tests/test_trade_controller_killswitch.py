from core.models import (BtstCandidate, Instrument, OrderResult, OrderType, Side,
                         TradeMode)
from services.risk_manager import RiskConfig
from services import trade_controller, kill_switch, audit
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
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="BO1", exec_price=req.price)


def _cand():
    return BtstCandidate(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        entry=100.0, target=103.0, stop=98.0, net_score=0.4, close_strength=0.9,
        volume_ratio=1.5, reasons=["x"], gap_risk="gap")


def test_confirm_halted_places_nothing_and_returns_halted(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "is_halted", lambda: True)
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "a.jsonl"))
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.status == "HALTED" and res.ok is False
    assert dhan.placed == []
    assert list_trades(conn) == []


def test_confirm_not_halted_places(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "is_halted", lambda: False)
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "a.jsonl"))
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.ok and len(dhan.placed) == 1


def test_confirm_halted_writes_audit(tmp_path, monkeypatch):
    apath = str(tmp_path / "a.jsonl")
    monkeypatch.setattr(kill_switch, "is_halted", lambda: True)
    monkeypatch.setattr(audit, "AUDIT_PATH", apath)
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=None)
    events = audit.read_events(path=apath)
    assert any(e["event"] == "HALTED" for e in events)
