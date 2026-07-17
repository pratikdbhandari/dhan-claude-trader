"""The token pre-flight must be visible before the open, on the pages actually
looked at during a session — not buried in a log line."""
from __future__ import annotations
from datetime import datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from core.models import Instrument
from services.market_clock import IST
from web.server import create_web_app
import web.deps as wdeps
import web.routes.live as live_mod

PAGES = ("/", "/live", "/settings")


def _tok(delta):
    return jwt.encode({"exp": int((datetime.now(IST) + delta).timestamp())},
                      "x", algorithm="HS256")


@pytest.fixture
def client(monkeypatch, fake_dhan):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [])
    monkeypatch.setattr(live_mod.market_feed, "load_universe",
                        lambda path="universe.json": [])
    return TestClient(create_web_app())


def _set_token(monkeypatch, token):
    real = wdeps.config_store.get_setting

    def fake(key, default=None, path=None):
        if key == "DHAN_ACCESS_TOKEN":
            return token
        return real(key, default) if path is None else real(key, default, path)
    monkeypatch.setattr(wdeps.config_store, "get_setting", fake)


def test_healthy_token_shows_no_banner(client, monkeypatch):
    _set_token(monkeypatch, _tok(timedelta(days=25)))
    for p in PAGES:
        t = client.get(p).text
        assert "Refresh token" not in t
        assert "EXPIRED" not in t


def test_token_dying_midsession_warns_on_every_page(client, monkeypatch):
    _set_token(monkeypatch, _tok(timedelta(minutes=30)))
    for p in PAGES:
        t = client.get(p).text
        assert "before the next 15:30 close" in t, f"no warning on {p}"
        assert "Refresh token" in t


def test_expired_token_warns_loudly(client, monkeypatch):
    _set_token(monkeypatch, _tok(timedelta(minutes=-5)))
    for p in PAGES:
        assert "EXPIRED" in client.get(p).text, f"no warning on {p}"


def test_missing_token_warns(client, monkeypatch):
    _set_token(monkeypatch, "")
    assert "No Dhan access token saved" in client.get("/").text


def test_settings_shows_expiry_time(client, monkeypatch):
    _set_token(monkeypatch, _tok(timedelta(days=25)))
    assert "expires" in client.get("/settings").text


def test_dashboard_does_not_claim_ai_when_signals_are_mock(client, monkeypatch):
    """The web signal path is hardcoded mode="mock" — no LLM is called, so the
    page must not tell the user an AI recommended the trade."""
    _set_token(monkeypatch, _tok(timedelta(days=25)))
    t = client.get("/").text
    assert "AI recommends" not in t
    assert "Indicator consensus" in t
