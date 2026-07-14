"""Settings page — read/write the same config_store keys the Streamlit Settings page uses."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core import config_store
from web.server import templates

router = APIRouter()
_val = lambda k, d="": config_store.get_setting(k, d)


@router.get("/settings", response_class=HTMLResponse)
def page(request: Request):
    keys = {k: _val(k) for k in ("DHAN_CLIENT_ID", "SIGNAL_SOURCE", "TRADE_MODE",
            "MAX_DAILY_LOSS", "MAX_RISK_PER_TRADE_PCT", "MAX_OPEN_POSITIONS",
            "ACCOUNT_CAPITAL", "BELL_ENABLED", "BELL_LEAD_MINUTES")}
    return templates.TemplateResponse("settings.html", {"request": request, "k": keys})


@router.post("/settings/save", response_class=HTMLResponse)
def save(request: Request, dhan_id: str = Form(""), dhan_token: str = Form(""),
         signal_source: str = Form("mock"), trade_mode: str = Form("PAPER"),
         max_daily_loss: str = Form("10000"), max_risk: str = Form("1.0"),
         max_pos: str = Form("2"), capital: str = Form("100000"),
         bell_enabled: str = Form("true"), bell_lead: str = Form("10")):
    updates = {"DHAN_CLIENT_ID": dhan_id, "SIGNAL_SOURCE": signal_source,
               "TRADE_MODE": trade_mode, "MAX_DAILY_LOSS": max_daily_loss,
               "MAX_RISK_PER_TRADE_PCT": max_risk, "MAX_OPEN_POSITIONS": max_pos,
               "ACCOUNT_CAPITAL": capital, "BELL_ENABLED": bell_enabled,
               "BELL_LEAD_MINUTES": bell_lead}
    if dhan_token:
        updates["DHAN_ACCESS_TOKEN"] = dhan_token
    config_store.save({k: v for k, v in updates.items() if v != ""})
    return HTMLResponse('<div class="banner ok">Settings saved.</div>')
