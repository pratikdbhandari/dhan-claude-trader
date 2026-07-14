"""Options page — expiries/chain via services.options_chain, the same data the desktop
Options page shows."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core.models import Instrument
from services.options_chain import get_expiries, get_chain
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/options", response_class=HTMLResponse)
def page(request: Request):
    syms = [i for i in deps.load_watchlist() if i.kind == "INDEX"]
    return templates.TemplateResponse("options.html", {"request": request, "syms": syms})


@router.post("/options/chain", response_class=HTMLResponse)
def chain(request: Request, symbol: str = Form(...), security_id: str = Form(...),
          exchange_segment: str = Form("IDX_I")):
    dhan = deps.get_dhan()
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="INDEX")
    expiries = get_expiries(instr, dhan)
    rows = get_chain(instr, expiries[0], dhan) if expiries else []
    return templates.TemplateResponse("partials/payoff.html",
                                      {"request": request, "expiries": expiries, "rows": rows})
