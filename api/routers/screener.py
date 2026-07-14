"""GET /screener — ranked current setups across the watchlist, using the same
algorithm services/screener.py already provides to the desktop Screener page."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.deps import get_dhan_client, load_watchlist
from services.screener import scan

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("")
def get_screener(user_id: str = Depends(require_user), dhan=Depends(get_dhan_client),
                 watchlist=Depends(load_watchlist)):
    def _candles_fn(instr):
        style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
        return dhan.get_candles(instr, interval=15 if style == "intraday" else "day",
                                lookback_days=10)

    return scan(watchlist, candles_fn=_candles_fn, active_ids=list(range(1, 30)))
