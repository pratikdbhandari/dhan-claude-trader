import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.models import Instrument
from api.auth import require_user
from api.deps import get_dhan_client, load_watchlist
from api.routers import screener


def _trending_candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def _app(dhan, watchlist):
    app = FastAPI()
    app.include_router(screener.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    app.dependency_overrides[load_watchlist] = lambda: watchlist
    return app


def test_get_screener_scans_watchlist(fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()
    client = TestClient(_app(fake_dhan, [instr]))

    resp = client.get("/screener")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


def test_get_screener_reports_error_row_for_bad_instrument(fake_dhan):
    instr = Instrument(symbol="BADSYM", exchange_segment="NSE_EQ", security_id="2")
    client = TestClient(_app(fake_dhan, [instr]))

    resp = client.get("/screener")

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["symbol"] == "BADSYM"
    assert "error" in body[0]


def test_screener_requires_auth(fake_dhan):
    app = FastAPI()
    app.include_router(screener.router)
    app.dependency_overrides[get_dhan_client] = lambda: fake_dhan
    app.dependency_overrides[load_watchlist] = lambda: []
    client = TestClient(app)

    resp = client.get("/screener")

    assert resp.status_code == 401
