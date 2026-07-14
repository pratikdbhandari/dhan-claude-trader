"""Shared fixtures for API tests. FakeDhan mirrors the pattern already used in
tests/test_trade_controller.py, extended with the read methods the API needs."""
from __future__ import annotations
import time

import jwt
import pytest

from core.models import OrderResult, TradeMode
from data.journal import init_db

TEST_JWT_SECRET = "test-secret-do-not-use-in-prod"


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []
        self.bracket = []
        self.positions = []
        self.fund_limits = {"availabelBalance": 100000}
        self.candles_by_symbol = {}

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        self.bracket.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="BO1", exec_price=req.price)

    def get_positions(self):
        return self.positions

    def get_fund_limits(self):
        return self.fund_limits

    def get_candles(self, instrument, interval, lookback_days=5):
        return self.candles_by_symbol.get(instrument.symbol)

    def exit_position(self, instrument):
        return OrderResult(ok=True, mode=self.mode, status="PLACED",
                           dhan_order_id=f"PAPER-EXIT-{instrument.symbol}")


@pytest.fixture
def fake_dhan():
    return FakeDhan()


@pytest.fixture
def temp_journal(tmp_path):
    return init_db(str(tmp_path / "test_trades.db"))


@pytest.fixture
def make_jwt(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)

    def _make(sub="user-1", exp_offset=3600):
        payload = {"sub": sub, "aud": "authenticated", "exp": time.time() + exp_offset}
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    return _make
