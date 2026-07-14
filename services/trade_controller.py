"""UI-less two-step order state machine. The no-auto-fire guarantee lives here:
no function places an order except confirm_and_place, and only when the pending
order's risk check passed."""
from __future__ import annotations
from dataclasses import dataclass
from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderResult,
                         OrderType, RiskCheck, Side, SignalType, TradeMode)
from services import risk_manager, kill_switch, audit
from services.risk_manager import RiskConfig


@dataclass
class PendingOrder:
    order_request: OrderRequest
    risk_check: RiskCheck


def build_order_request(consensus: ConsensusSignal, instrument: Instrument, qty: int,
                        order_type: OrderType = OrderType.MARKET) -> OrderRequest:
    snap = consensus.indicator_snapshot
    side = Side.BUY if consensus.consensus is SignalType.BUY else Side.SELL
    return OrderRequest(
        instrument=instrument, side=side, order_type=order_type, qty=qty,
        price=snap.get("entry"), stop_loss=snap.get("stop_loss"),
        target=snap.get("target"), source_signal=consensus)


def prepare_order(consensus: ConsensusSignal, instrument: Instrument, *,
                  equity: float, cfg: RiskConfig, day_pnl_value: float,
                  open_count: int, order_type: OrderType = OrderType.MARKET
                  ) -> PendingOrder:
    snap = consensus.indicator_snapshot
    entry, stop = snap.get("entry"), snap.get("stop_loss")
    qty = risk_manager.position_size(equity, entry, stop, cfg.max_risk_per_trade_pct) \
        if (entry is not None and stop is not None) else 0
    req = build_order_request(consensus, instrument, qty, order_type)
    check = risk_manager.pre_trade_check(req, cfg, equity=equity,
                                         day_pnl_value=day_pnl_value,
                                         open_count=open_count)
    audit.log_event("PREPARE", {"symbol": instrument.symbol, "allowed": check.allowed})
    return PendingOrder(order_request=req, risk_check=check)


def confirm_and_place(pending: PendingOrder, *, dhan_client, journal_conn,
                      consensus: ConsensusSignal | None = None) -> OrderResult:
    """The ONLY path that places an order. Halted or risk-blocked orders never reach
    the broker. The kill-switch check is the first statement — structurally
    unbypassable, like the no-auto-fire guarantee."""
    req = pending.order_request
    if kill_switch.is_halted():
        audit.log_event("HALTED", {"symbol": req.instrument.symbol})
        return OrderResult(ok=False, mode=dhan_client.mode, status="HALTED",
                           error_message="Trading halted by kill-switch.")
    if not pending.risk_check.allowed:
        audit.log_event("BLOCKED", {"symbol": req.instrument.symbol,
                                    "reasons": pending.risk_check.reasons})
        return OrderResult(ok=False, mode=dhan_client.mode, status="BLOCKED",
                           error_message="; ".join(pending.risk_check.reasons))
    if req.stop_loss is not None and req.target is not None:
        result = dhan_client.place_bracket_order(req)
    else:
        result = dhan_client.place_order(req)
    audit.log_event("PLACED", {"symbol": req.instrument.symbol, "side": req.side.value,
                               "qty": req.qty, "order_id": result.dhan_order_id,
                               "status": result.status})
    if journal_conn is not None:
        from data.journal import log_order
        log_order(journal_conn, req, result, consensus=consensus)
    return result


def prepare_btst_order(candidate, *, equity: float, cfg: RiskConfig,
                       day_pnl_value: float, open_count: int) -> PendingOrder:
    """Build a CNC (delivery) MARKET buy for a BTST candidate and run the same
    pre-trade risk gate. Target/stop live in the plan (journal + BTST book), not a
    broker bracket, so the OrderRequest carries no stop_loss/target — confirm_and_place
    therefore routes to plain place_order (CNC), never place_bracket_order."""
    qty = risk_manager.position_size(equity, candidate.entry, candidate.stop,
                                     cfg.max_risk_per_trade_pct)
    req = OrderRequest(
        instrument=candidate.instrument, side=Side.BUY, order_type=OrderType.MARKET,
        qty=qty, price=candidate.entry, stop_loss=None, target=None,
        product_type="CNC")
    check = risk_manager.pre_trade_check(req, cfg, equity=equity,
                                         day_pnl_value=day_pnl_value,
                                         open_count=open_count)
    audit.log_event("PREPARE", {"symbol": candidate.instrument.symbol,
                                "allowed": check.allowed})
    return PendingOrder(order_request=req, risk_check=check)
