"""Backtest page — simulate + walk-forward / Monte-Carlo / bootstrap robustness verdict."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from services import backtest, backtest_robust
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/backtest", response_class=HTMLResponse)
def page(request: Request):
    syms = [i.symbol for i in deps.load_watchlist()] or ["NIFTY"]
    return templates.TemplateResponse("backtest.html", {"request": request, "syms": syms})


@router.post("/backtest/run", response_class=HTMLResponse)
def run(request: Request, symbol: str = Form(...), style: str = Form("positional")):
    dhan = deps.get_dhan()
    instr = next((i for i in deps.load_watchlist() if i.symbol == symbol), None)
    ctx = {"request": request, "result": None, "verdict": None, "wf": None, "mc": None, "ci": None}
    if instr is None:
        return templates.TemplateResponse("partials/backtest_result.html", ctx)
    candles = deps.candles_for(dhan, instr) if style != "positional" else \
        dhan.get_candles(instr, interval="day", lookback_days=365)
    seg = "equity_intraday" if style == "intraday" else "equity_delivery"
    sim_kw = {"active_ids": list(range(1, 30)), "style": style, "segment": seg, "warmup": 200}
    result = backtest.simulate(candles, **sim_kw)
    if result.n_trades < 10:
        ctx["insufficient"] = result.n_trades
        return templates.TemplateResponse("partials/backtest_result.html", ctx)
    wf = backtest_robust.walk_forward(candles, n_splits=4, sim_kwargs=sim_kw)
    mc = backtest_robust.monte_carlo_drawdown(result)
    ci = backtest_robust.bootstrap_ci(result)
    ctx.update({"result": result, "verdict": backtest_robust.robustness_verdict(wf, mc, ci),
                "wf": wf, "mc": mc, "ci": ci})
    return templates.TemplateResponse("partials/backtest_result.html", ctx)
