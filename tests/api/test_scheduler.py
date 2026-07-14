import asyncio

import numpy as np
import pandas as pd

from core.models import Instrument, SignalType
from services.risk_manager import RiskConfig
from api.scheduler import run_tick, scheduler_loop
from api.state import PendingStore


def _trending_candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def test_run_tick_stores_a_signal_and_pushes_once(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()
    store = PendingStore(ttl_seconds=300)
    pushed = []

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda pid, i, cs: pushed.append((pid, i.symbol, cs.consensus)),
             signal_source="mock")

    active = store.list_active()
    assert len(active) <= 1
    if active:
        assert len(pushed) == 1
        assert pushed[0][1] == "RELIANCE"


def test_run_tick_skips_instrument_with_insufficient_candles(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles(n=5)
    store = PendingStore(ttl_seconds=300)

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda *a: (_ for _ in ()).throw(AssertionError("should not push")))

    assert store.list_active() == []


def test_run_tick_continues_after_one_instrument_raises(fake_dhan, temp_journal):
    ok_instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    bad_instr = Instrument(symbol="BADSYM", exchange_segment="NSE_EQ", security_id="2")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()

    def _raising_get_candles(instrument, interval, lookback_days=5):
        if instrument.symbol == "BADSYM":
            raise RuntimeError("candle fetch exploded")
        return fake_dhan.candles_by_symbol.get(instrument.symbol)
    fake_dhan.get_candles = _raising_get_candles

    store = PendingStore(ttl_seconds=300)
    pushed = []

    run_tick(watchlist=[bad_instr, ok_instr], dhan_client=fake_dhan,
             journal_conn=temp_journal, cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda pid, i, cs: pushed.append(i.symbol), signal_source="mock")

    assert "BADSYM" not in pushed


def test_run_tick_does_nothing_when_globally_blocked(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()
    cfg = RiskConfig(max_open_positions=0)
    store = PendingStore(ttl_seconds=300)

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=cfg, equity=100000, store=store,
             push_fn=lambda *a: (_ for _ in ()).throw(AssertionError("should not push")))

    assert store.list_active() == []


def test_scheduler_loop_calls_tick_fn_until_stopped():
    calls = {"n": 0}

    def tick_fn():
        calls["n"] += 1

    async def _run():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.gather(
            scheduler_loop(interval_seconds=0, tick_fn=tick_fn, stop_event=stop_event),
            stopper(),
        )

    asyncio.run(_run())
    assert calls["n"] >= 1


def test_scheduler_loop_survives_tick_fn_raising():
    calls = {"n": 0}

    def tick_fn():
        calls["n"] += 1
        raise RuntimeError("boom")

    async def _run():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.gather(
            scheduler_loop(interval_seconds=0, tick_fn=tick_fn, stop_event=stop_event),
            stopper(),
        )

    asyncio.run(_run())
    assert calls["n"] >= 1
