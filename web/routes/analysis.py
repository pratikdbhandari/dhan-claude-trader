"""Full analysis page — /analysis/{symbol}. Structured verdict on whether the
trade should be taken or avoided: confluence votes, quality gate, trade plan
with suggested size, positive/negative news for the share, fundamentals."""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from services import analysis as analysis_svc
from services import risk_manager
from services.dhan_client import DhanError
from web import deps
from web.routes.live import _chart_symbols
from web.server import templates

router = APIRouter()


@router.get("/analysis/{symbol}", response_class=HTMLResponse)
def page(request: Request, symbol: str):
    instr = next((i for i in _chart_symbols() if i.symbol == symbol.upper()), None)
    if instr is None:
        raise HTTPException(404, f"unknown symbol {symbol}")
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    style = deps.style_for(instr.kind)
    err = None
    a = None
    qty = None
    try:
        df = deps.candles_for(dhan, instr)
        if df is None or len(df) < 30:
            err = "Not enough candle data to analyse right now — retry shortly."
        else:
            a = analysis_svc.analyze(instr, df, style=style)
            if a["entry"] is not None and a["stop_loss"] is not None:
                cfg = deps.get_risk_config()
                equity = deps.get_equity(mode, dhan)
                qty = risk_manager.position_size(
                    equity, a["entry"], a["stop_loss"], cfg.max_risk_per_trade_pct)
    except DhanError as e:
        err = str(e)
    return templates.TemplateResponse("analysis.html", {
        "request": request, "symbol": instr.symbol, "kind": instr.kind,
        "a": a, "err": err, "qty": qty, "mode": mode,
        "chart_interval": "day" if style == "positional" else "15"})
