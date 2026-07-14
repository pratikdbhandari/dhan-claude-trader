"""GET /signals/pending and POST /signals/{id}/confirm — the phone's only write
path into the order-placement pipeline. Preparation happens in the scheduler
(api/scheduler.py); this router cannot create a confirmable entry, only resolve
one that the scheduler already prepared and risk-checked."""
from __future__ import annotations
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_user
from api.deps import get_dhan_client, get_journal, get_pending_store
from api.schemas import ConfirmResponse, PendingSignalOut, RiskCheckOut
from services import trade_controller

router = APIRouter(prefix="/signals", tags=["signals"])


def _to_out(stored) -> PendingSignalOut:
    req = stored.pending.order_request
    rc = stored.pending.risk_check
    return PendingSignalOut(
        pending_id=stored.pending_id, symbol=req.instrument.symbol,
        side=req.side.value, qty=req.qty, entry=req.price,
        stop_loss=req.stop_loss, target=req.target,
        consensus=stored.consensus.consensus.value,
        avg_confidence=stored.consensus.avg_confidence,
        agreement_pct=stored.consensus.agreement_pct,
        risk_check=RiskCheckOut(**asdict(rc)))


@router.get("/pending", response_model=list[PendingSignalOut])
def list_pending(user_id: str = Depends(require_user),
                 store=Depends(get_pending_store)):
    return [_to_out(s) for s in store.list_active()]


@router.post("/{pending_id}/confirm", response_model=ConfirmResponse)
def confirm(pending_id: str, user_id: str = Depends(require_user),
           store=Depends(get_pending_store), dhan=Depends(get_dhan_client),
           journal=Depends(get_journal)):
    stored = store.pop(pending_id)
    if stored is None:
        raise HTTPException(status_code=404,
                            detail="signal expired or already resolved")
    result = trade_controller.confirm_and_place(
        stored.pending, dhan_client=dhan, journal_conn=journal,
        consensus=stored.consensus)
    return ConfirmResponse(ok=result.ok, status=result.status,
                           dhan_order_id=result.dhan_order_id,
                           exec_price=result.exec_price,
                           error_message=result.error_message)
