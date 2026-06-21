"""UI-less two-step order state machine. The no-auto-fire guarantee lives here:
no function places an order except confirm_and_place, and only when the pending
order's risk check passed."""
from __future__ import annotations
from dataclasses import dataclass
from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderResult,
                         OrderType, RiskCheck, Side, SignalType, TradeMode)
from services import risk_manager
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
    return PendingOrder(order_request=req, risk_check=check)


def confirm_and_place(pending: PendingOrder, *, dhan_client, journal_conn,
                      consensus: ConsensusSignal | None = None) -> OrderResult:
    """The ONLY path that places an order. Blocked orders never reach the broker."""
    if not pending.risk_check.allowed:
        return OrderResult(ok=False, mode=dhan_client.mode, status="BLOCKED",
                           error_message="; ".join(pending.risk_check.reasons))
    req = pending.order_request
    if req.stop_loss is not None and req.target is not None:
        result = dhan_client.place_bracket_order(req)
    else:
        result = dhan_client.place_order(req)
    if journal_conn is not None:
        from data.journal import log_order
        log_order(journal_conn, req, result, consensus=consensus)
    return result
