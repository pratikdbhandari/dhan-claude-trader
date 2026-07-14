import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from core.models import Instrument
from web.server import create_web_app
from web.routes import dashboard as dash
import web.deps as wdeps


def _candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan, temp_journal, watchlist):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": watchlist)
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(dash.kill_switch, "is_halted", lambda: False)
    return TestClient(create_web_app())


def test_dashboard_page_renders(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])
    r = c.get("/")
    assert r.status_code == 200
    assert "Dhan-Claude" in r.text
    assert "Today P&amp;L" in r.text or "Today P&L" in r.text


def test_signals_partial_lists_instruments(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])
    r = c.get("/partials/signals")
    assert r.status_code == 200
    assert "RELIANCE" in r.text


def test_signals_partial_shows_insufficient_when_no_candles(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="ZZZ", exchange_segment="NSE_EQ", security_id="9")
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])
    r = c.get("/partials/signals")
    assert r.status_code == 200
    assert "insufficient" in r.text.lower()
