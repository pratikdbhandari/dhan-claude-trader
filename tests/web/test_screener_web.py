import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from core.models import Instrument
from web.server import create_web_app
import web.deps as wdeps


def _candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close+1, "low": close-1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_screener_page_renders(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.get("/screener")
    assert r.status_code == 200 and "Run scan" in r.text


def test_screener_run_returns_rows(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.post("/screener/run")
    assert r.status_code == 200 and "RELIANCE" in r.text
