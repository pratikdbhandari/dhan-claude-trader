"""GET /options/expiries, GET /options/chain, POST /options/payoff — wrappers over
options_chain.py (live Dhan data) and options_payoff.py (pure math), the same data
the desktop Options page shows."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.deps import get_dhan_client
from api.schemas import PayoffOut, PayoffRequest
from core.models import Instrument
from services.options_chain import get_chain, get_expiries
from services.options_payoff import metrics, payoff_curve

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/expiries")
def expiries(symbol: str, exchange_segment: str, security_id: str,
            user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="OPTION")
    return get_expiries(instr, dhan)


@router.get("/chain")
def chain(symbol: str, exchange_segment: str, security_id: str, expiry: str,
         user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="OPTION")
    return get_chain(instr, expiry, dhan)


@router.post("/payoff", response_model=PayoffOut)
def payoff(req: PayoffRequest, user_id: str = Depends(require_user)):
    legs = [leg.model_dump() for leg in req.legs]
    m = metrics(legs, req.spot_ref)
    lo, hi = req.spot_ref * 0.7, req.spot_ref * 1.3
    xs, ys = payoff_curve(legs, lo, hi)
    return PayoffOut(xs=xs, ys=ys, **m)
