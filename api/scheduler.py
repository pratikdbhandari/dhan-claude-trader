"""Background signal-preparation loop. Runs the exact same pipeline app.py's
auto-refresh runs (confluence -> signal_engine.generate -> quality gate ->
trade_controller.prepare_order), on a fixed cadence, independent of whether the
desktop UI is open. This is where 'prepare' happens for the mobile flow — the
phone's only call is POST /signals/{id}/confirm (see routers/signals.py), which
can only resolve an entry this loop already created and risk-checked."""
from __future__ import annotations
import asyncio
import logging

from core.models import Instrument, SignalType, TradeMode
from data.journal import to_legs
from services import indicators as ind
from services import risk_manager, signal_engine, trade_controller
from services.dhan_client import DhanError
from services.quality_gate import apply_gate
from services.sizing import quality_multiplier
from services.strategies.engine import build_confluence

log = logging.getLogger(__name__)


def run_tick(*, watchlist: list[Instrument], dhan_client, journal_conn,
            cfg: risk_manager.RiskConfig, equity: float, store, push_fn,
            signal_source: str = "mock", signal_cache: dict | None = None,
            event_flags: list[str] | None = None) -> None:
    """One pass over the watchlist. Never lets one bad instrument stop the rest."""
    signal_cache = signal_cache if signal_cache is not None else {}
    event_flags = event_flags or []
    mode_str = "LIVE" if dhan_client.mode is TradeMode.LIVE else "PAPER"
    legs = to_legs(journal_conn, mode=mode_str)
    try:
        dpnl = risk_manager.day_pnl(dhan_client.mode, dhan_client=dhan_client,
                                    legs=legs, ltp_fn=lambda s: None)
        open_count = risk_manager.open_position_count(
            dhan_client.mode, dhan_client=dhan_client, legs=legs)
    except DhanError:
        log.exception("risk read failed this tick; skipping")
        return
    globally_blocked = (dpnl <= -cfg.max_daily_loss
                       or open_count >= cfg.max_open_positions)
    if globally_blocked:
        return

    for instr in watchlist:
        try:
            style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
            candles = dhan_client.get_candles(
                instr, interval=15 if style == "intraday" else "day",
                lookback_days=10 if style == "intraday" else 400)
            if candles is None or len(candles) < 30:
                continue
            snap = build_confluence(candles, regime=None, style=style,
                                    active_ids=list(range(1, 30)))
            last = float(candles["close"].iloc[-1])
            atr = float(ind.atr(candles).dropna().iloc[-1])
            cs = signal_engine.generate(
                instr, snap, last_price=last, atr=atr, mode=signal_source,
                cache=signal_cache)
            if cs.consensus is SignalType.HOLD:
                continue
            gate = apply_gate(cs, fundamentals={}, event_flags=event_flags,
                              kind=instr.kind)
            if not gate.passed:
                continue

            fingerprint = (f"{instr.symbol}:{cs.consensus.value}:"
                          f"{cs.indicator_snapshot.get('entry')}:"
                          f"{cs.indicator_snapshot.get('stop_loss')}")
            if store.already_pushed(fingerprint):
                continue

            pending = trade_controller.prepare_order(
                cs, instr, equity=equity, cfg=cfg, day_pnl_value=dpnl,
                open_count=open_count)
            mult = min(1.0, quality_multiplier(gate.score))
            if mult < 1.0:
                pending.order_request.qty = max(1, int(pending.order_request.qty * mult))

            pending_id = store.add(pending, cs)
            store.mark_pushed(fingerprint)
            push_fn(pending_id, instr, cs)
        except Exception:                                  # noqa: BLE001
            log.exception("tick failed for %s; continuing", instr.symbol)
            continue


async def scheduler_loop(*, interval_seconds: int, tick_fn, stop_event: asyncio.Event) -> None:
    """Runs tick_fn() immediately, then every interval_seconds, until stop_event is
    set. tick_fn takes no args — callers close over their own dependencies."""
    while not stop_event.is_set():
        try:
            tick_fn()
        except Exception:                                  # noqa: BLE001
            log.exception("scheduler tick raised unexpectedly")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
