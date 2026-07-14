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


def _client(monkeypatch, fake_dhan, temp_journal, halted=False):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(dash.kill_switch, "is_halted", lambda: halted)
    return TestClient(create_web_app()), fake_dhan


def test_confirm_returns_dialog(monkeypatch, fake_dhan, temp_journal):
    c, _ = _client(monkeypatch, fake_dhan, temp_journal)
    r = c.get("/dashboard/confirm/RELIANCE")
    assert r.status_code == 200
    assert "Place" in r.text and "RELIANCE" in r.text


def test_get_confirm_does_not_place(monkeypatch, fake_dhan, temp_journal):
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal)
    c.get("/dashboard/confirm/RELIANCE")
    assert dhan.placed == [] and dhan.bracket == []


def test_place_places_order_and_journals(monkeypatch, fake_dhan, temp_journal):
    from data.journal import list_trades
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal)
    r = c.post("/dashboard/place/RELIANCE")
    assert r.status_code == 200
    assert (len(dhan.placed) + len(dhan.bracket)) == 1
    assert len(list_trades(temp_journal)) == 1


def test_place_refused_when_halted(monkeypatch, fake_dhan, temp_journal):
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal, halted=True)
    r = c.post("/dashboard/place/RELIANCE")
    assert r.status_code == 200
    assert "HALTED" in r.text.upper()
    assert dhan.placed == [] and dhan.bracket == []
