"""BTST page — near-close scan + overnight book (services.btst + market_clock)."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services import btst, market_clock
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from data.journal import open_btst_book
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/btst", response_class=HTMLResponse)
def page(request: Request):
    now = datetime.now(timezone.utc)
    dhan = deps.get_dhan()

    def candles_fn(instr):
        return dhan.get_candles(instr, interval="day", lookback_days=400)

    def confluence_fn(df):
        return build_confluence(df, regime=None, style="positional", active_ids=list(range(1, 30)))

    candidates = btst.scan(deps.load_watchlist(), candles_fn=candles_fn,
                           confluence_fn=confluence_fn, active_ids=list(range(1, 30)))
    book = open_btst_book(deps.get_journal(), mode=deps.get_mode())
    return templates.TemplateResponse("btst.html", {
        "request": request, "near_close": market_clock.is_near_close(now),
        "candidates": candidates[:10], "book": book})
