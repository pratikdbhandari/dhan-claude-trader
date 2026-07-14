"""GET /reports/pnl and GET /reports/eod — read-only wrappers over accounting +
eod_report, the same data the desktop Reports page shows."""
from __future__ import annotations
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from api.auth import require_user
from api.deps import get_journal
from data.journal import to_legs
from services.accounting import pnl_statement
from services.eod_report import build_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/pnl")
def get_pnl(mode: str = Query("PAPER"), period: str = Query("all"),
           period_key: str | None = Query(None),
           user_id: str = Depends(require_user), journal=Depends(get_journal)):
    legs = to_legs(journal, mode=mode)
    stmt = pnl_statement(legs, mode=mode, period=period, period_key=period_key,
                         ltp_fn=lambda s: None)
    return asdict(stmt)


@router.get("/eod")
def get_eod(mode: str = Query("PAPER"), date: str | None = Query(None),
           user_id: str = Depends(require_user), journal=Depends(get_journal)):
    return build_report(journal, mode=mode, date_key=date)
