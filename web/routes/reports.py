"""Reports page — P&L, equity curve, provider accuracy, AI cost, behavior, audit."""
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from data.journal import to_legs
from services import behavior, charting, audit, cost
from services.accounting import pnl_statement, realized_trades
from services.eod_report import build_report
from ui import themes
from web import deps, charts
from web.server import templates

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request, mode: str = "PAPER"):
    journal = deps.get_journal()
    legs = to_legs(journal, mode=mode)
    stmt = pnl_statement(legs, mode=mode, period="all", period_key=None, ltp_fn=lambda s: None)
    trades = realized_trades(legs, mode=mode)
    cc = themes.chart_colors()
    disp = behavior.disposition_effect(trades)
    rep = build_report(journal, mode=mode)
    runs = cost.read_runs()
    return templates.TemplateResponse("reports.html", {
        "request": request, "mode": mode, "stmt": asdict(stmt),
        "equity_json": charts.fig_json(charting.equity_curve(trades, colors=cc)),
        "accuracy_json": charts.fig_json(charting.provider_accuracy(rep.get("leaderboard", []), colors=cc)),
        "disp": disp, "cost_today": cost.summary(runs, "day"),
        "cost_month": cost.summary(runs, "month"),
        "audit": audit.read_events(limit=50)})
