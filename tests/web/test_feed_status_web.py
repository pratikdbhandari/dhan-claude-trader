"""The live-price partials must never present stale prices as live.
Reproduces the mid-session broker death (token expiry) end-to-end."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from core.models import Instrument
from services import market_feed
from web.server import create_web_app
import web.deps as wdeps
import web.routes.live as live_mod

NIFTY_ROW = {"last_price": 24140.3,
             "ohlc": {"open": 24142.1, "close": 24078.5, "high": 24167.4,
                      "low": 24097.05}}


class FakeSDK:
    def __init__(self):
        self.ok = True

    def ohlc_data(self, securities):
        if not self.ok:                       # broker dead (expired token)
            return {"status": "failure", "remarks": "Invalid token", "data": ""}
        return {"status": "success",
                "data": {"data": {"IDX_I": {"13": NIFTY_ROW}}, "status": "success"}}


def _reset():
    market_feed._cache.update(key=None, ts=0.0, rows={}, ok_wall=0.0)
    market_feed._last_call_ts = 0.0


@pytest.fixture
def client(monkeypatch, fake_dhan):
    sdk = FakeSDK()
    fake_dhan.sdk = sdk
    nifty = Instrument(symbol="NIFTY", exchange_segment="IDX_I",
                       security_id="13", kind="INDEX")
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [nifty])
    monkeypatch.setattr(live_mod.market_feed, "load_universe",
                        lambda path="universe.json": [])
    _reset()
    yield TestClient(create_web_app()), sdk
    _reset()


def test_healthy_feed_shows_live_not_warning(client):
    c, _ = client
    for url in ("/live/partials/ticker", "/live/partials/watch"):
        t = c.get(url).text
        assert "PRICES NOT LIVE" not in t
        assert "live · updated" in t
        assert "is-stale" not in t


def test_dead_broker_midsession_warns_instead_of_faking_live(client):
    c, sdk = client
    fresh = c.get("/live/partials/ticker").text
    assert "24,140.30" in fresh and "PRICES NOT LIVE" not in fresh

    # broker dies, and the last good snapshot ages past the threshold
    sdk.ok = False
    market_feed._cache["ts"] = 0.0                              # force a refresh attempt
    market_feed._cache["ok_wall"] -= market_feed.STALE_AFTER + 5

    t = c.get("/live/partials/ticker").text
    assert "PRICES NOT LIVE" in t          # loud warning
    assert "is-stale" in t                 # prices visually drained
    assert "24,140.30" in t                # last price still shown, but flagged
    assert "/settings" in t                # points at the likely cause (token)
    assert "PRICES NOT LIVE" in c.get("/live/partials/watch").text


def test_recovery_clears_the_warning(client):
    """Token refreshed mid-session -> banner must clear on the next poll."""
    c, sdk = client
    c.get("/live/partials/ticker")
    sdk.ok = False
    market_feed._cache["ts"] = 0.0
    market_feed._cache["ok_wall"] -= market_feed.STALE_AFTER + 5
    assert "PRICES NOT LIVE" in c.get("/live/partials/ticker").text

    sdk.ok = True
    market_feed._cache["ts"] = 0.0
    market_feed._last_call_ts = 0.0
    t = c.get("/live/partials/ticker").text
    assert "PRICES NOT LIVE" not in t and "live · updated" in t
