"""Analysis page route: renders verdict/pros/cons for a known symbol, 404s on
unknown, degrades gracefully on thin data. Fake dhan + no network."""
from __future__ import annotations
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from core.models import Instrument
from web.server import create_web_app
import web.deps as wdeps
import web.routes.live as live_mod
from services import analysis as analysis_svc


def _candles(n=250):
    rng = np.random.default_rng(5)
    close = 100 + np.linspace(0, 30, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan, watchlist):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": watchlist)
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(live_mod.market_feed, "load_universe",
                        lambda path="universe.json": [])
    # keep the page offline: no RSS / yfinance
    monkeypatch.setattr(analysis_svc, "cached_headlines",
                        lambda ttl=300.0, fetch=None: [
                            "Reliance wins big order, shares jump",
                            "Nifty ends flat ahead of Fed decision"])
    monkeypatch.setattr(analysis_svc, "cached_fundamentals",
                        lambda symbol, kind, ttl=1800.0: {
                            "pe": 25.0, "eps": 55.0, "market_cap": 2e12,
                            "promoter_pct": 50.4, "institution_pct": 28.1})
    import services.global_markets as gm
    monkeypatch.setattr(gm, "snapshot", lambda ttl=600.0, fetch=None: {
        "^GSPC": {"name": "S&P 500", "ticker": "^GSPC", "group": "US",
                  "last": 7500.0, "pct": 1.2},
        "^TNX": {"name": "US 10Y yield", "ticker": "^TNX", "group": "US",
                 "last": 4.5, "pct": -0.8}})
    return TestClient(create_web_app())


def test_analysis_page_renders_verdict_and_news(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, [instr])
    r = c.get("/analysis/RELIANCE")
    assert r.status_code == 200
    for needle in ("Trade plan", "Why this trade could work", "News impact",
                   "Strategy votes", "Fundamentals", "Global drivers",
                   "Promoter holding", "50.4%"):
        assert needle in r.text
    assert "Reliance wins big order" in r.text
    assert "Corporate events" in r.text          # "wins big order" → ORDERS bucket


def test_analysis_unknown_symbol_404(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan, [])
    assert c.get("/analysis/NOPE").status_code == 404


def test_analysis_thin_data_shows_error_banner(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles(10)   # < 30 bars
    c = _client(monkeypatch, fake_dhan, [instr])
    r = c.get("/analysis/RELIANCE")
    assert r.status_code == 200
    assert "Not enough candle data" in r.text


def test_screener_rows_link_to_analysis(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, [instr])
    r = c.post("/screener/run", data={"scope": "watchlist", "signals_only": "false"})
    assert r.status_code == 200
    assert "/analysis/RELIANCE" in r.text
