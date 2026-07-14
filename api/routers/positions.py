"""GET /positions and POST /positions/{security_id}/exit — thin wrappers over
dhan_client, the same calls app.py's positions panel makes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_user
from api.deps import get_dhan_client
from core.models import Instrument
from services.dhan_client import DhanError

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
def list_positions(user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    try:
        return dhan.get_positions()
    except DhanError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{security_id}/exit")
def exit_position(security_id: str, exchange_segment: str, symbol: str,
                  user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="EQUITY")
    result = dhan.exit_position(instr)
    return {"ok": result.ok, "status": result.status,
           "dhan_order_id": result.dhan_order_id,
           "error_message": result.error_message}
