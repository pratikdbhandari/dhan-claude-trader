"""Screener page — ranked trade setups via services.screener.scan, over the
watchlist or the full NIFTY-50 universe. Every row links to /analysis/{symbol}
for the full take-it-or-avoid-it breakdown."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from services.screener import scan
from services import market_feed
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
def run(request: Request, scope: str = Form("watchlist"),
        signals_only: str = Form("false")):
    if scope == "nifty50":
        instruments = market_feed.load_universe()
    else:
        instruments = deps.load_watchlist()
    dhan = deps.get_dhan()
    rows = scan(instruments, candles_fn=lambda i: deps.candles_for(dhan, i),
                active_ids=list(range(1, 30)),
                signals_only=(signals_only == "true"))
    return templates.TemplateResponse("partials/screener_rows.html",
                                      {"request": request, "rows": rows})
