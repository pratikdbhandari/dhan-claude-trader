"""GET/PUT /settings/risk and GET /settings/readiness — the existing risk-limit
config store and 5-gate Go-Live checklist, the same data the desktop
Settings/Go-Live pages show. This does not change what limits exist, only lets
the phone read/write the existing values."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.schemas import GateOut, ReadinessOut, RiskSettingsIn, RiskSettingsOut
from core import config_store, readiness

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/risk", response_model=RiskSettingsOut)
def get_risk(user_id: str = Depends(require_user)):
    return RiskSettingsOut(
        max_daily_loss=float(config_store.get_setting("MAX_DAILY_LOSS", "10000")),
        max_risk_per_trade_pct=float(
            config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0")),
        max_open_positions=int(config_store.get_setting("MAX_OPEN_POSITIONS", "2")))


@router.put("/risk", response_model=RiskSettingsOut)
def put_risk(body: RiskSettingsIn, user_id: str = Depends(require_user)):
    updates = {}
    if body.max_daily_loss is not None:
        updates["MAX_DAILY_LOSS"] = str(body.max_daily_loss)
    if body.max_risk_per_trade_pct is not None:
        updates["MAX_RISK_PER_TRADE_PCT"] = str(body.max_risk_per_trade_pct)
    if body.max_open_positions is not None:
        updates["MAX_OPEN_POSITIONS"] = str(body.max_open_positions)
    config_store.save(updates)
    return get_risk(user_id)


@router.get("/readiness", response_model=ReadinessOut)
def get_readiness(user_id: str = Depends(require_user)):
    state = readiness.get_state()
    gates = [GateOut(id=gid, label=label, kind=kind, passed=bool(state.get(gid)))
            for gid, label, kind in readiness.GATES]
    return ReadinessOut(gates=gates, passed_count=readiness.passed_count(),
                        all_passed=readiness.all_passed())
