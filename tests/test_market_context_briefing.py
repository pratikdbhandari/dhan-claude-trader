from datetime import date
import numpy as np
import pandas as pd
from services.market_context import build_context
from services.briefing import morning_briefing, narrative
from services.strategy_selector import select
from core.models import Instrument


def _index():
    return Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                      kind="INDEX")


class FakeDhan:
    def __init__(self, candles=None, ltp=14.5, fail=False):
        self._c = candles
        self._ltp = ltp
        self._fail = fail

    def get_candles(self, instrument, interval, lookback_days):
        if self._fail:
            from services.dhan_client import DhanError
            raise DhanError("no data")
        return self._c

    def get_ltp(self, instrument):
        return self._ltp


def _trending_candles(n=120):
    close = 100 + np.linspace(0, 40, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)})


def test_build_context_populates_fields():
    dhan = FakeDhan(candles=_trending_candles(), ltp=13.2)
    ctx = build_context(_index(), vix_instrument=_index(), dhan_client=dhan,
                        news_fetch=lambda url: "<rss><channel></channel></rss>",
                        today=date(2026, 6, 22))  # Monday
    assert ctx.regime in ("TRENDING", "RANGING", "VOLATILE")
    assert ctx.vix == 13.2
    assert ctx.index_rsi is not None
    assert "EXPIRY" not in ctx.event_flags


def test_thursday_flags_expiry():
    dhan = FakeDhan(candles=_trending_candles())
    ctx = build_context(_index(), dhan_client=dhan,
                        news_fetch=lambda url: "<rss></rss>",
                        today=date(2026, 6, 25))  # Thursday
    assert "EXPIRY" in ctx.event_flags


def test_context_degrades_on_data_failure():
    dhan = FakeDhan(fail=True)
    ctx = build_context(_index(), dhan_client=dhan,
                        news_fetch=lambda url: "<rss></rss>", today=date(2026, 6, 22))
    assert ctx.regime == "UNKNOWN" and ctx.index_rsi is None


def test_morning_briefing_mock_mode():
    dhan = FakeDhan(candles=_trending_candles(), ltp=13.0)
    out = morning_briefing(_index(), vix_instrument=_index(), dhan_client=dhan,
                           mode="mock", news_fetch=lambda url: "<rss></rss>",
                           today=date(2026, 6, 22))
    assert out["selection"].preset in ("intraday_momentum", "range_scalper")
    assert out["selection"].preset in out["narrative"]


def test_narrative_api_falls_back_on_provider_error():
    from services.market_context import MarketContext
    ctx = MarketContext(regime="TRENDING", vix=14, index_rsi=55, rsi_state="NEUTRAL")
    sel = select(ctx)

    def boom(prompt):
        raise RuntimeError("api down")
    text = narrative(ctx, sel, mode="api", provider={"name": "groq", "model": "m"},
                     client=boom)
    assert sel.preset in text   # fell back to template
