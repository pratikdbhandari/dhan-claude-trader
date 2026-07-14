import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from core.models import Instrument
from web.server import create_web_app
import web.deps as wdeps


def _trend(n=1400):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 120, n) + rng.normal(0, 1.0, n)
    return pd.DataFrame({"open": np.concatenate([[close[0]], close[:-1]]),
                         "high": close+1, "low": close-1, "close": close,
                         "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trend()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_backtest_page_renders(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.get("/backtest")
    assert r.status_code == 200 and "Run backtest" in r.text


def test_backtest_run_returns_result_or_insufficient(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.post("/backtest/run", data={"symbol": "RELIANCE", "style": "positional"})
    assert r.status_code == 200
    assert ("robust" in r.text.lower()) or ("insufficient" in r.text.lower())
