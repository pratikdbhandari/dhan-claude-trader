"""FastAPI app assembly: wires auth, routers, and the background scheduler
together. Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000

create_app(start_scheduler=False) is used by tests so a hermetic test run never
depends on real Dhan/Supabase/FCM credentials or network access — the scheduler
loop is the only piece of this module with an external side effect on startup."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import push, supabase_client
from api.deps import (get_dhan_client, get_equity, get_journal, get_pending_store,
                      get_risk_config, load_watchlist)
from api.routers import options, positions, push as push_router, reports, screener, settings, signals
from api.scheduler import run_tick, scheduler_loop
from core import config_store


def _make_push_fn():
    def _push(pending_id, instrument, consensus):
        title = f"New signal: {instrument.symbol} {consensus.consensus.value}"
        for token in supabase_client.list_push_tokens():
            push.send_push(token, title, "Review now", data={"pending_id": pending_id})
    return _push


def _tick() -> None:
    dhan = get_dhan_client()
    journal = get_journal()
    cfg = get_risk_config()
    watchlist = load_watchlist()
    mode = config_store.get_setting("TRADE_MODE", "PAPER")
    equity = get_equity(mode, dhan)
    run_tick(watchlist=watchlist, dhan_client=dhan, journal_conn=journal, cfg=cfg,
            equity=equity, store=get_pending_store(), push_fn=_make_push_fn(),
            signal_source=config_store.get_setting("SIGNAL_SOURCE", "mock"))


def create_app(*, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop_event = asyncio.Event()
        task = None
        if start_scheduler:
            interval = int(config_store.get_setting("SIGNAL_COOLDOWN_SECONDS", "300"))
            task = asyncio.create_task(
                scheduler_loop(interval_seconds=interval, tick_fn=_tick,
                               stop_event=stop_event))
        yield
        stop_event.set()
        if task is not None:
            await task

    app = FastAPI(title="Dhan-Claude Trader API", lifespan=lifespan)
    app.include_router(signals.router)
    app.include_router(positions.router)
    app.include_router(reports.router)
    app.include_router(screener.router)
    app.include_router(options.router)
    app.include_router(settings.router)
    app.include_router(push_router.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
