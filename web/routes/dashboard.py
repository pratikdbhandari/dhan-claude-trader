"""Dashboard routes — risk panel + live signal cards, mirroring app.py's signal loop.
Read path here; the two-step confirm/place is appended in Task 4."""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from core.models import SignalType, TradeMode
from data.journal import to_legs
from services import indicators as ind
from services import risk_manager, signal_engine, kill_switch
from services.dhan_client import DhanError
from services.quality_gate import apply_gate
from services.sizing import quality_multiplier
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from services import trade_controller
from web import deps
from web.server import templates

router = APIRouter()


def _risk_panel(mode, dhan, journal, cfg):
    legs = to_legs(journal, mode=mode)
    try:
        dpnl = risk_manager.day_pnl(TradeMode(mode), dhan_client=dhan, legs=legs,
                                    ltp_fn=lambda s: None)
        open_count = risk_manager.open_position_count(TradeMode(mode), dhan_client=dhan,
                                                      legs=legs)
        err = None
    except DhanError as e:
        dpnl, open_count, err = 0.0, 0, str(e)
    buffer = max(0.0, cfg.max_daily_loss + dpnl)
    blocked = dpnl <= -cfg.max_daily_loss or open_count >= cfg.max_open_positions
    return {"dpnl": dpnl, "open_count": open_count, "buffer": buffer,
            "blocked": blocked, "err": err}


def _build_cards(mode, dhan, cfg, panel):
    cards = []
    for instr in deps.load_watchlist():
        try:
            candles = deps.candles_for(dhan, instr)
            if candles is None or len(candles) < 30:
                cards.append({"symbol": instr.symbol, "insufficient": True})
                continue
            style = deps.style_for(instr.kind)
            snap = build_confluence(candles, regime=None, style=style,
                                    active_ids=list(range(1, 30)))
            last = float(candles["close"].iloc[-1])
            atr = float(ind.atr(candles).dropna().iloc[-1])
            cs = signal_engine.generate(instr, snap, last_price=last, atr=atr,
                                        mode="mock", cache={})
            gate = apply_gate(cs, fundamentals={}, event_flags=[], kind=instr.kind)
            sd = cs.indicator_snapshot
            cards.append({
                "symbol": instr.symbol, "regime": snap.regime.value,
                "signal": cs.consensus.value, "cls": cs.consensus.value.lower(),
                "conf": cs.avg_confidence, "agree": cs.agreement_pct,
                "entry": sd.get("entry"), "sl": sd.get("stop_loss"), "tgt": sd.get("target"),
                "quality": gate.score,
                "qlabel": "PASS" if gate.passed else ("VETO" if gate.vetoed else "LOW"),
                "qpass": gate.passed,
                "selectable": cs.consensus is not SignalType.HOLD and gate.passed
                and not panel["blocked"],
                "insufficient": False})
        except DhanError as e:
            cards.append({"symbol": instr.symbol, "error": str(e)})
    return cards


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    panel = _risk_panel(mode, dhan, deps.get_journal(), cfg)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "mode": mode, "panel": panel, "cfg": cfg,
        "halted": kill_switch.is_halted()})


@router.get("/partials/signals", response_class=HTMLResponse)
def signals_partial(request: Request):
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    panel = _risk_panel(mode, dhan, deps.get_journal(), cfg)
    cards = _build_cards(mode, dhan, cfg, panel)
    return templates.TemplateResponse("partials/signals.html",
                                      {"request": request, "cards": cards})


@router.get("/partials/blank", response_class=HTMLResponse)
def blank():
    return HTMLResponse("")


# ---------------------------------------------------------------- confirm / place (Task 4)
def _prepare_for(symbol: str):
    """Re-derive the pending order server-side for `symbol` from fresh candles.
    Returns (instrument, consensus, gate, pending, panel, mode, dhan, journal) or None."""
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    journal = deps.get_journal()
    panel = _risk_panel(mode, dhan, journal, cfg)
    instr = next((i for i in deps.load_watchlist() if i.symbol == symbol), None)
    if instr is None:
        return None
    candles = deps.candles_for(dhan, instr)
    if candles is None or len(candles) < 30:
        return None
    style = deps.style_for(instr.kind)
    snap = build_confluence(candles, regime=None, style=style, active_ids=list(range(1, 30)))
    last = float(candles["close"].iloc[-1])
    atr = float(ind.atr(candles).dropna().iloc[-1])
    cs = signal_engine.generate(instr, snap, last_price=last, atr=atr, mode="mock", cache={})
    gate = apply_gate(cs, fundamentals={}, event_flags=[], kind=instr.kind)
    equity = deps.get_equity(mode, dhan)
    pending = trade_controller.prepare_order(cs, instr, equity=equity, cfg=cfg,
                                             day_pnl_value=panel["dpnl"],
                                             open_count=panel["open_count"])
    mult = min(1.0, quality_multiplier(gate.score))
    if mult < 1.0:
        pending.order_request.qty = max(1, int(pending.order_request.qty * mult))
    return instr, cs, gate, pending, panel, mode, dhan, journal


@router.get("/dashboard/confirm/{symbol}", response_class=HTMLResponse)
def confirm(request: Request, symbol: str):
    got = _prepare_for(symbol)
    if got is None:
        raise HTTPException(404, "signal unavailable")
    instr, cs, gate, pending, panel, *_ = got
    req = pending.order_request
    return templates.TemplateResponse("partials/confirm_dialog.html", {
        "request": request, "symbol": symbol, "req": req,
        "rc": pending.risk_check, "halted": kill_switch.is_halted(),
        "gate_pass": gate.passed})


@router.post("/dashboard/place/{symbol}", response_class=HTMLResponse)
def place(request: Request, symbol: str):
    if kill_switch.is_halted():
        return templates.TemplateResponse("partials/place_result.html",
                                          {"request": request, "status": "HALTED",
                                           "ok": False, "symbol": symbol})
    got = _prepare_for(symbol)
    if got is None:
        raise HTTPException(404, "signal unavailable")
    instr, cs, gate, pending, panel, mode, dhan, journal = got
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan,
                                             journal_conn=journal, consensus=cs)
    return templates.TemplateResponse("partials/place_result.html", {
        "request": request, "status": res.status, "ok": res.ok, "symbol": symbol})


@router.post("/dashboard/halt", response_class=HTMLResponse)
def halt(request: Request):
    kill_switch.halt("manual halt from web dashboard")
    return HTMLResponse("")


@router.post("/dashboard/resume", response_class=HTMLResponse)
def resume(request: Request):
    kill_switch.resume()
    return HTMLResponse("")
