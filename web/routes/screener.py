"""Screener page — ranked setups across the watchlist via services.screener.scan."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.screener import scan
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/screener", response_class=HTMLResponse)
def screener(request: Request):
    return templates.TemplateResponse("screener.html", {"request": request})


@router.post("/screener/run", response_class=HTMLResponse)
def run(request: Request):
    dhan = deps.get_dhan()
    rows = scan(deps.load_watchlist(), candles_fn=lambda i: deps.candles_for(dhan, i),
                active_ids=list(range(1, 30)), signals_only=False)
    return templates.TemplateResponse("partials/screener_rows.html",
                                      {"request": request, "rows": rows})
