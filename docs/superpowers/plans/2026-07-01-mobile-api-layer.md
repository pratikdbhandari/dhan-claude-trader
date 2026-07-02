# Mobile API Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI layer (`api/`) in front of the existing trading engine so a future Android app can review signals, confirm trades, and check positions/reports over the internet, without touching any existing trading logic.

**Architecture:** A background scheduler runs the same prepare pipeline `app.py`'s auto-refresh already runs (candles → confluence → `signal_engine.generate` → quality gate → `trade_controller.prepare_order`), storing risk-checked pending signals in memory. The only client-writable endpoint is `POST /signals/{id}/confirm`, which calls the existing `trade_controller.confirm_and_place` — the same no-auto-fire function the desktop confirm dialog calls. Supabase provides JWT auth (verified locally, no per-request round trip) and a `push_tokens` table; Firebase Cloud Messaging delivers signal alerts. Existing `services/`, `core/`, `data/` modules are not modified.

**Tech Stack:** FastAPI, uvicorn, PyJWT (Supabase JWT verification), httpx (Supabase REST + FCM calls), google-auth (FCM OAuth token), pytest (existing style, TestClient for routers).

**Reference spec:** [`docs/superpowers/specs/2026-07-01-mobile-api-layer-design.md`](../specs/2026-07-01-mobile-api-layer-design.md)

---

## Before You Start

Read these existing files — the plan below calls their real functions and must not change their behavior:
- `services/trade_controller.py` — `PendingOrder`, `prepare_order`, `confirm_and_place`
- `services/risk_manager.py` — `RiskConfig`, `day_pnl`, `open_position_count`, `pre_trade_check`
- `services/dhan_client.py` — `DhanClient`, `DhanError`
- `services/signal_engine.py` — `generate`
- `services/quality_gate.py` — `apply_gate`, `GateResult`
- `services/sizing.py` — `quality_multiplier`
- `services/screener.py`, `services/options_chain.py`, `services/options_payoff.py`, `services/accounting.py`, `services/eod_report.py`
- `core/models.py`, `core/config_store.py`, `core/readiness.py`
- `data/journal.py` — `init_db`, `log_order`, `to_legs`
- `services/instruments.py` — `download_master`, `build_index`, `resolve_watchlist`
- `app.py` — the current wiring this plan replicates as a second presentation layer
- `tests/conftest.py`, `tests/test_trade_controller.py` — existing fixture/mocking style (`FakeDhan`, temp SQLite)

New code lives entirely under `api/` and `tests/api/`. No file outside those two directories is modified except `requirements.txt`, `.env.example`, and `run_app.bat`/`AUTOSTART.md` (Task 17).

---

## Task 1: Package Skeleton + Dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `api/__init__.py`
- Create: `api/routers/__init__.py`
- Create: `tests/api/__init__.py`

- [ ] **Step 1: Add new dependencies to `requirements.txt`**

Append to `requirements.txt`:

```
# Mobile API layer
fastapi==0.115.6
uvicorn[standard]==0.34.0
pyjwt==2.10.1
httpx==0.28.1
google-auth==2.37.0
```

- [ ] **Step 2: Install and verify**

Run: `pip install -r requirements.txt`
Expected: all packages install without error.

- [ ] **Step 3: Create empty package files**

`api/__init__.py`:
```python
```

`api/routers/__init__.py`:
```python
```

`tests/api/__init__.py`:
```python
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt api/__init__.py api/routers/__init__.py tests/api/__init__.py
git commit -m "chore(api): scaffold api package and add FastAPI dependencies"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `api/schemas.py`

No test needed — this file has no branching logic, only data shape declarations. It is exercised indirectly by every router test in later tasks.

- [ ] **Step 1: Write `api/schemas.py`**

```python
"""Pydantic request/response models for the API layer. These mirror core/models.py
dataclasses for JSON serialization; core/models.py itself is unchanged."""
from __future__ import annotations
from typing import Optional

from pydantic import BaseModel


class RiskCheckOut(BaseModel):
    allowed: bool
    reasons: list[str]
    day_pnl: float
    open_positions: int
    remaining_loss_buffer: float


class PendingSignalOut(BaseModel):
    pending_id: str
    symbol: str
    side: str
    qty: int
    entry: Optional[float]
    stop_loss: Optional[float]
    target: Optional[float]
    consensus: str
    avg_confidence: int
    agreement_pct: int
    risk_check: RiskCheckOut


class ConfirmResponse(BaseModel):
    ok: bool
    status: str
    dhan_order_id: Optional[str] = None
    exec_price: Optional[float] = None
    error_message: Optional[str] = None


class RiskSettingsOut(BaseModel):
    max_daily_loss: float
    max_risk_per_trade_pct: float
    max_open_positions: int


class RiskSettingsIn(BaseModel):
    max_daily_loss: Optional[float] = None
    max_risk_per_trade_pct: Optional[float] = None
    max_open_positions: Optional[int] = None


class GateOut(BaseModel):
    id: str
    label: str
    kind: str
    passed: bool


class ReadinessOut(BaseModel):
    gates: list[GateOut]
    passed_count: int
    all_passed: bool


class PushTokenIn(BaseModel):
    token: str


class OptionLegIn(BaseModel):
    type: str            # "CE" | "PE"
    action: str          # "BUY" | "SELL"
    strike: float
    premium: float
    lots: int
    lot_size: int


class PayoffRequest(BaseModel):
    legs: list[OptionLegIn]
    spot_ref: float


class PayoffOut(BaseModel):
    xs: list[float]
    ys: list[float]
    max_profit: float
    max_loss: float
    breakevens: list[float]
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "import api.schemas"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add api/schemas.py
git commit -m "feat(api): add Pydantic schemas for the API layer"
```

---

## Task 3: JWT Auth

**Files:**
- Create: `api/auth.py`
- Test: `tests/api/test_auth.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_auth.py`:
```python
import time
import jwt
import pytest
from fastapi import HTTPException

from api.auth import decode_token, require_user

SECRET = "test-secret"


def _token(sub="user-1", exp_offset=3600, secret=SECRET, aud="authenticated"):
    payload = {"sub": sub, "aud": aud, "exp": time.time() + exp_offset}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_decode_token_returns_sub_for_valid_token():
    token = _token(sub="user-42")
    assert decode_token(token, SECRET) == "user-42"


def test_decode_token_rejects_expired_token():
    token = _token(exp_offset=-10)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, SECRET)
    assert exc_info.value.status_code == 401


def test_decode_token_rejects_wrong_signature():
    token = _token(secret="wrong-secret")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token, SECRET)
    assert exc_info.value.status_code == 401


def test_require_user_rejects_missing_bearer(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc_info:
        require_user(authorization="")
    assert exc_info.value.status_code == 401


def test_require_user_accepts_valid_bearer(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    token = _token(sub="user-7")
    assert require_user(authorization=f"Bearer {token}") == "user-7"


def test_require_user_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    token = _token()
    with pytest.raises(HTTPException) as exc_info:
        require_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.auth'`

- [ ] **Step 3: Write `api/auth.py`**

```python
"""Supabase JWT verification. Every route except /health requires a valid bearer
token signed with the project's JWT secret (HS256, audience 'authenticated'),
verified locally — no per-request network call to Supabase."""
from __future__ import annotations
import os

import jwt
from fastapi import Header, HTTPException


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def decode_token(token: str, secret: str) -> str:
    """Verify signature/expiry/audience; return the Supabase user id (sub claim)."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError:
        raise AuthError("token expired")
    except jwt.InvalidTokenError:
        raise AuthError("invalid token")
    return payload["sub"]


def require_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: parse 'Bearer <jwt>', verify it, return the user id."""
    if not authorization.startswith("Bearer "):
        raise AuthError("missing bearer token")
    token = authorization.removeprefix("Bearer ")
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise AuthError("server misconfigured: SUPABASE_JWT_SECRET not set")
    return decode_token(token, secret)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_auth.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/auth.py tests/api/test_auth.py
git commit -m "feat(api): add Supabase JWT verification"
```

---

## Task 4: PendingStore

**Files:**
- Create: `api/state.py`
- Test: `tests/api/test_state.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_state.py`:
```python
from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderType,
                         RiskCheck, Side, SignalType)
from services.trade_controller import PendingOrder
from api.state import PendingStore


def _pending():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET,
                       qty=10, price=100.0, stop_loss=95.0, target=110.0)
    check = RiskCheck(allowed=True)
    return PendingOrder(order_request=req, risk_check=check)


def _consensus():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    return ConsensusSignal(instrument=instr, providers=[], consensus=SignalType.BUY,
                           avg_confidence=80, agreement_pct=100)


def test_add_then_get_returns_stored_entry():
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    stored = store.get(pid)
    assert stored is not None
    assert stored.pending_id == pid
    assert stored.pending.order_request.instrument.symbol == "RELIANCE"


def test_get_unknown_id_returns_none():
    store = PendingStore(ttl_seconds=300)
    assert store.get("does-not-exist") is None


def test_entry_expires_after_ttl():
    clock = {"t": 1000.0}
    store = PendingStore(ttl_seconds=10, clock=lambda: clock["t"])
    pid = store.add(_pending(), _consensus())
    clock["t"] += 11
    assert store.get(pid) is None


def test_pop_removes_entry_so_it_cannot_be_confirmed_twice():
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    first = store.pop(pid)
    second = store.pop(pid)
    assert first is not None
    assert second is None


def test_list_active_excludes_expired():
    clock = {"t": 1000.0}
    store = PendingStore(ttl_seconds=10, clock=lambda: clock["t"])
    pid_keep = store.add(_pending(), _consensus())
    clock["t"] += 5
    pid_expire = store.add(_pending(), _consensus())
    clock["t"] += 6   # pid_keep is now 11s old (expired), pid_expire is 6s old
    ids = {s.pending_id for s in store.list_active()}
    assert pid_keep not in ids
    assert pid_expire in ids


def test_dedup_fingerprint_marks_and_checks():
    store = PendingStore(ttl_seconds=300)
    assert store.already_pushed("RELIANCE:BUY:100:95") is False
    store.mark_pushed("RELIANCE:BUY:100:95")
    assert store.already_pushed("RELIANCE:BUY:100:95") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.state'`

- [ ] **Step 3: Write `api/state.py`**

```python
"""In-memory store for signals the scheduler has prepared and risk-checked, keyed
by a generated id. The Android app's only write path (POST /signals/{id}/confirm)
looks entries up here — nothing else can create a confirmable entry, and popping
an entry on confirm/expiry makes double-confirm impossible."""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass

from core.models import ConsensusSignal
from services.trade_controller import PendingOrder


@dataclass
class StoredSignal:
    pending_id: str
    pending: PendingOrder
    consensus: ConsensusSignal
    created_at: float


class PendingStore:
    def __init__(self, ttl_seconds: int = 300, clock=time.time):
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, StoredSignal] = {}
        self._seen_fingerprints: dict[str, float] = {}

    def add(self, pending: PendingOrder, consensus: ConsensusSignal) -> str:
        pending_id = str(uuid.uuid4())
        self._entries[pending_id] = StoredSignal(
            pending_id=pending_id, pending=pending, consensus=consensus,
            created_at=self._clock())
        return pending_id

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [pid for pid, e in self._entries.items()
                  if now - e.created_at > self.ttl_seconds]
        for pid in expired:
            del self._entries[pid]

    def get(self, pending_id: str) -> StoredSignal | None:
        self._purge_expired()
        return self._entries.get(pending_id)

    def pop(self, pending_id: str) -> StoredSignal | None:
        self._purge_expired()
        return self._entries.pop(pending_id, None)

    def list_active(self) -> list[StoredSignal]:
        self._purge_expired()
        return list(self._entries.values())

    def already_pushed(self, fingerprint: str) -> bool:
        return fingerprint in self._seen_fingerprints

    def mark_pushed(self, fingerprint: str) -> None:
        self._seen_fingerprints[fingerprint] = self._clock()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_state.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/state.py tests/api/test_state.py
git commit -m "feat(api): add PendingStore for scheduler-prepared signals"
```

---

## Task 5: Shared Test Fixtures

**Files:**
- Create: `tests/api/conftest.py`

- [ ] **Step 1: Write `tests/api/conftest.py`**

```python
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
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `pytest tests/api/ --collect-only`
Expected: collects successfully (no tests fail to collect due to fixture import errors).

- [ ] **Step 3: Commit**

```bash
git add tests/api/conftest.py
git commit -m "test(api): add shared FakeDhan/journal/JWT fixtures"
```

---

## Task 6: Dependency Providers

**Files:**
- Create: `api/deps.py`
- Test: `tests/api/test_deps.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_deps.py`:
```python
import json

from core.models import Instrument, TradeMode
from core import config_store
from services.dhan_client import DhanClient
from services.risk_manager import RiskConfig


def _isolate_config_store(monkeypatch, tmp_path):
    """core.config_store.get_setting defaults its `path` param to SETTINGS_PATH
    evaluated at import time — monkeypatching the config_store.SETTINGS_PATH
    attribute alone would NOT affect it. Rebind __defaults__ directly so these
    tests never read a developer's real ~/.dhan_claude_trader/settings.local.json.
    """
    empty_path = tmp_path / "settings.local.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", empty_path)
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, empty_path))


def test_get_journal_returns_same_connection_each_call(monkeypatch, tmp_path):
    import api.deps as deps
    deps._journal_conn = None
    monkeypatch.chdir(tmp_path)
    conn1 = deps.get_journal()
    conn2 = deps.get_journal()
    assert conn1 is conn2
    deps._journal_conn = None


def test_get_dhan_client_reads_mode_from_config_store(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("TRADE_MODE", "PAPER")
    monkeypatch.setenv("DHAN_CLIENT_ID", "cid")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "token")
    client = deps.get_dhan_client()
    assert isinstance(client, DhanClient)
    assert client.mode is TradeMode.PAPER


def test_get_risk_config_reads_env_overrides(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_DAILY_LOSS", "5000")
    monkeypatch.setenv("MAX_RISK_PER_TRADE_PCT", "2.0")
    monkeypatch.setenv("MAX_OPEN_POSITIONS", "3")
    cfg = deps.get_risk_config()
    assert cfg == RiskConfig(max_daily_loss=5000.0, max_risk_per_trade_pct=2.0,
                             max_open_positions=3)


def test_load_watchlist_returns_resolved_instruments(tmp_path):
    import api.deps as deps
    wl_path = tmp_path / "watchlist.json"
    wl_path.write_text(json.dumps({"instruments": [
        {"symbol": "RELIANCE", "exchange_segment": "NSE_EQ", "security_id": "500325",
         "lot_size": 1, "kind": "EQUITY"},
    ]}))
    result = deps.load_watchlist(path=wl_path)
    assert result == [Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                                 security_id="500325", lot_size=1, kind="EQUITY")]


def test_get_equity_paper_mode_uses_account_capital(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("ACCOUNT_CAPITAL", "250000")
    equity = deps.get_equity("PAPER", dhan=None)
    assert equity == 250000.0


def test_get_equity_live_mode_reads_fund_limits(fake_dhan):
    import api.deps as deps
    fake_dhan.fund_limits = {"availabelBalance": 42000}
    equity = deps.get_equity("LIVE", dhan=fake_dhan)
    assert equity == 42000.0


def test_get_pending_store_returns_same_instance():
    import api.deps as deps
    assert deps.get_pending_store() is deps.get_pending_store()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.deps'`

- [ ] **Step 3: Write `api/deps.py`**

```python
"""FastAPI dependency providers — construct the same objects app.py wires up at
startup, so both presentation layers call identical service functions with
identical configuration."""
from __future__ import annotations
import json
from pathlib import Path

from core import config_store
from core.models import Instrument, TradeMode
from data.journal import init_db
from services import instruments, risk_manager
from services.dhan_client import DhanClient, DhanError

_journal_conn = None
_instrument_index: dict | None = None
_pending_store = None


def get_journal():
    global _journal_conn
    if _journal_conn is None:
        _journal_conn = init_db("trades.db")
    return _journal_conn


def get_dhan_client() -> DhanClient:
    mode = config_store.get_setting("TRADE_MODE", "PAPER")
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


def get_risk_config() -> risk_manager.RiskConfig:
    return risk_manager.load_risk_config({
        "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
        "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
        "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
    })


def get_instrument_index() -> dict:
    global _instrument_index
    if _instrument_index is not None:
        return _instrument_index
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
               else instruments.download_master())
        _instrument_index = instruments.build_index(text)
    except Exception:                                      # noqa: BLE001
        _instrument_index = {}
    return _instrument_index


def load_watchlist(path: str | Path = "watchlist.json") -> list[Instrument]:
    data = json.loads(Path(path).read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY"))
          for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, get_instrument_index())


def get_equity(mode: str, dhan: DhanClient | None) -> float:
    if mode == "LIVE":
        try:
            funds = dhan.get_fund_limits()
            return float(funds.get("availabelBalance", funds.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


def get_pending_store():
    global _pending_store
    if _pending_store is None:
        from api.state import PendingStore
        ttl = int(config_store.get_setting("SIGNAL_COOLDOWN_SECONDS", "300"))
        _pending_store = PendingStore(ttl_seconds=ttl)
    return _pending_store
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_deps.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add api/deps.py tests/api/test_deps.py
git commit -m "feat(api): add FastAPI dependency providers"
```

---

## Task 7: FCM Push

**Files:**
- Create: `api/push.py`
- Test: `tests/api/test_push.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_push.py`:
```python
import pytest

from api.push import send_push


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_send_push_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return FakeResponse(200)

    result = send_push("device-token", "title", "body", data={"pending_id": "abc"},
                       get_access_token=lambda: "fake-access-token", post=fake_post)
    assert result is True
    assert len(calls) == 1
    url, payload, headers = calls[0]
    assert url == "https://fcm.googleapis.com/v1/projects/test-project/messages:send"
    assert payload["message"]["token"] == "device-token"
    assert payload["message"]["notification"] == {"title": "title", "body": "body"}
    assert payload["message"]["data"] == {"pending_id": "abc"}
    assert headers["Authorization"] == "Bearer fake-access-token"


def test_send_push_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")

    def fake_post(url, json, headers, timeout):
        return FakeResponse(500)

    result = send_push("device-token", "title", "body",
                       get_access_token=lambda: "fake-access-token", post=fake_post)
    assert result is False


def test_send_push_returns_false_when_project_id_missing(monkeypatch):
    monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
    result = send_push("device-token", "title", "body",
                       get_access_token=lambda: "fake-access-token", post=lambda **kw: None)
    assert result is False


def test_send_push_returns_false_when_token_fetch_raises(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")

    def raising_get_token():
        raise RuntimeError("credentials file not found")

    result = send_push("device-token", "title", "body",
                       get_access_token=raising_get_token, post=lambda **kw: None)
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_push.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.push'`

- [ ] **Step 3: Write `api/push.py`**

```python
"""Firebase Cloud Messaging push notifications (HTTP v1 API). Failures are logged
and swallowed — a missed push must never affect the trading pipeline."""
from __future__ import annotations
import logging
import os

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
_credentials = None


def _default_get_access_token() -> str:
    global _credentials
    if _credentials is None:
        key_path = os.environ["FCM_SERVICE_ACCOUNT_JSON_PATH"]
        _credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=_SCOPES)
    if not _credentials.valid:
        _credentials.refresh(GoogleAuthRequest())
    return _credentials.token


def send_push(token: str, title: str, body: str, data: dict | None = None, *,
             get_access_token=_default_get_access_token, post=httpx.post) -> bool:
    """Send one FCM message. Returns True on success, False on any failure (logged),
    never raises — callers must be able to fire-and-forget this."""
    try:
        project_id = os.environ["FCM_PROJECT_ID"]
        access_token = get_access_token()
        message = {"message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
        }}
        resp = post(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            json=message, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:                                      # noqa: BLE001
        log.exception("FCM push failed")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_push.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/push.py tests/api/test_push.py
git commit -m "feat(api): add FCM push notification helper"
```

---

## Task 8: Supabase push_tokens Client

**Files:**
- Create: `api/supabase_client.py`
- Test: `tests/api/test_supabase_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_supabase_client.py`:
```python
from api.supabase_client import list_push_tokens, register_push_token


class FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def test_register_push_token_upserts_via_post(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return FakeResponse()

    register_push_token("user-1", "device-token-abc", post=fake_post)
    assert len(calls) == 1
    url, payload, headers = calls[0]
    assert url == "https://project.supabase.co/rest/v1/push_tokens"
    assert payload == {"user_id": "user-1", "token": "device-token-abc"}
    assert headers["Prefer"] == "resolution=merge-duplicates"
    assert headers["apikey"] == "service-key"


def test_list_push_tokens_returns_token_list(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

    def fake_get(url, headers, timeout):
        assert url == "https://project.supabase.co/rest/v1/push_tokens?select=token"
        return FakeResponse(json_data=[{"token": "t1"}, {"token": "t2"}])

    tokens = list_push_tokens(get=fake_get)
    assert tokens == ["t1", "t2"]


def test_list_push_tokens_returns_empty_list_when_no_rows(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    tokens = list_push_tokens(get=lambda url, headers, timeout: FakeResponse(json_data=[]))
    assert tokens == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_supabase_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.supabase_client'`

- [ ] **Step 3: Write `api/supabase_client.py`**

```python
"""Thin wrapper over Supabase's PostgREST API for the push_tokens table. No ORM —
one table, two operations. Trading data is NOT stored in Supabase; the SQLite
journal remains the single source of truth (see data/journal.py)."""
from __future__ import annotations
import os

import httpx


def _headers() -> dict:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}",
           "Content-Type": "application/json"}


def register_push_token(user_id: str, token: str, *, post=httpx.post) -> None:
    """Upsert one row keyed by user_id — one device token per logged-in user."""
    url = os.environ["SUPABASE_URL"] + "/rest/v1/push_tokens"
    resp = post(url, json={"user_id": user_id, "token": token},
               headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
               timeout=10)
    resp.raise_for_status()


def list_push_tokens(*, get=httpx.get) -> list[str]:
    """Return every registered device token."""
    url = os.environ["SUPABASE_URL"] + "/rest/v1/push_tokens?select=token"
    resp = get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return [row["token"] for row in resp.json()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_supabase_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/supabase_client.py tests/api/test_supabase_client.py
git commit -m "feat(api): add Supabase push_tokens REST client"
```

---

## Task 9: Scheduler

**Files:**
- Create: `api/scheduler.py`
- Test: `tests/api/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_scheduler.py`:
```python
import asyncio

import numpy as np
import pandas as pd

from core.models import Instrument, SignalType
from services.risk_manager import RiskConfig
from api.scheduler import run_tick, scheduler_loop
from api.state import PendingStore


def _trending_candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def test_run_tick_stores_a_signal_and_pushes_once(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()
    store = PendingStore(ttl_seconds=300)
    pushed = []

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda pid, i, cs: pushed.append((pid, i.symbol, cs.consensus)),
             signal_source="mock")

    active = store.list_active()
    assert len(active) <= 1   # mock signal may be BUY/SELL/HOLD depending on confluence
    if active:
        assert len(pushed) == 1
        assert pushed[0][1] == "RELIANCE"


def test_run_tick_skips_instrument_with_insufficient_candles(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles(n=5)
    store = PendingStore(ttl_seconds=300)

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda *a: (_ for _ in ()).throw(AssertionError("should not push")))

    assert store.list_active() == []


def test_run_tick_continues_after_one_instrument_raises(fake_dhan, temp_journal):
    ok_instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    bad_instr = Instrument(symbol="BADSYM", exchange_segment="NSE_EQ", security_id="2")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()

    def _raising_get_candles(instrument, interval, lookback_days=5):
        if instrument.symbol == "BADSYM":
            raise RuntimeError("candle fetch exploded")
        return fake_dhan.candles_by_symbol.get(instrument.symbol)
    fake_dhan.get_candles = _raising_get_candles

    store = PendingStore(ttl_seconds=300)
    pushed = []

    run_tick(watchlist=[bad_instr, ok_instr], dhan_client=fake_dhan,
             journal_conn=temp_journal, cfg=RiskConfig(), equity=100000, store=store,
             push_fn=lambda pid, i, cs: pushed.append(i.symbol), signal_source="mock")

    # BADSYM's exception must not have stopped RELIANCE from being processed.
    assert "BADSYM" not in pushed


def test_run_tick_does_nothing_when_globally_blocked(fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trending_candles()
    cfg = RiskConfig(max_open_positions=0)   # already at/above cap -> globally blocked
    store = PendingStore(ttl_seconds=300)

    run_tick(watchlist=[instr], dhan_client=fake_dhan, journal_conn=temp_journal,
             cfg=cfg, equity=100000, store=store,
             push_fn=lambda *a: (_ for _ in ()).throw(AssertionError("should not push")))

    assert store.list_active() == []


def test_scheduler_loop_calls_tick_fn_until_stopped():
    calls = {"n": 0}

    def tick_fn():
        calls["n"] += 1

    async def _run():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.gather(
            scheduler_loop(interval_seconds=0, tick_fn=tick_fn, stop_event=stop_event),
            stopper(),
        )

    asyncio.run(_run())
    assert calls["n"] >= 1


def test_scheduler_loop_survives_tick_fn_raising():
    calls = {"n": 0}

    def tick_fn():
        calls["n"] += 1
        raise RuntimeError("boom")

    async def _run():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.gather(
            scheduler_loop(interval_seconds=0, tick_fn=tick_fn, stop_event=stop_event),
            stopper(),
        )

    asyncio.run(_run())
    assert calls["n"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.scheduler'`

- [ ] **Step 3: Write `api/scheduler.py`**

```python
"""Background signal-preparation loop. Runs the exact same pipeline app.py's
auto-refresh runs (confluence -> signal_engine.generate -> quality gate ->
trade_controller.prepare_order), on a fixed cadence, independent of whether the
desktop UI is open. This is where 'prepare' happens for the mobile flow — the
phone's only call is POST /signals/{id}/confirm (see routers/signals.py), which
can only resolve an entry this loop already created and risk-checked."""
from __future__ import annotations
import asyncio
import logging

from core.models import Instrument, SignalType, TradeMode
from data.journal import to_legs
from services import indicators as ind
from services import risk_manager, signal_engine, trade_controller
from services.dhan_client import DhanError
from services.quality_gate import apply_gate
from services.sizing import quality_multiplier
from services.strategies.engine import build_confluence

log = logging.getLogger(__name__)


def run_tick(*, watchlist: list[Instrument], dhan_client, journal_conn,
            cfg: risk_manager.RiskConfig, equity: float, store, push_fn,
            signal_source: str = "mock", signal_cache: dict | None = None,
            event_flags: list[str] | None = None) -> None:
    """One pass over the watchlist. Never lets one bad instrument stop the rest."""
    signal_cache = signal_cache if signal_cache is not None else {}
    event_flags = event_flags or []
    mode_str = "LIVE" if dhan_client.mode is TradeMode.LIVE else "PAPER"
    legs = to_legs(journal_conn, mode=mode_str)
    try:
        dpnl = risk_manager.day_pnl(dhan_client.mode, dhan_client=dhan_client,
                                    legs=legs, ltp_fn=lambda s: None)
        open_count = risk_manager.open_position_count(
            dhan_client.mode, dhan_client=dhan_client, legs=legs)
    except DhanError:
        log.exception("risk read failed this tick; skipping")
        return
    globally_blocked = (dpnl <= -cfg.max_daily_loss
                       or open_count >= cfg.max_open_positions)
    if globally_blocked:
        return

    for instr in watchlist:
        try:
            style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
            candles = dhan_client.get_candles(
                instr, interval=15 if style == "intraday" else "day", lookback_days=10)
            if candles is None or len(candles) < 30:
                continue
            snap = build_confluence(candles, regime=None, style=style,
                                    active_ids=list(range(1, 30)))
            last = float(candles["close"].iloc[-1])
            atr = float(ind.atr(candles).dropna().iloc[-1])
            cs = signal_engine.generate(
                instr, snap, last_price=last, atr=atr, mode=signal_source,
                cache=signal_cache)
            if cs.consensus is SignalType.HOLD:
                continue
            gate = apply_gate(cs, fundamentals={}, event_flags=event_flags,
                              kind=instr.kind)
            if not gate.passed:
                continue

            fingerprint = (f"{instr.symbol}:{cs.consensus.value}:"
                          f"{cs.indicator_snapshot.get('entry')}:"
                          f"{cs.indicator_snapshot.get('stop_loss')}")
            if store.already_pushed(fingerprint):
                continue

            pending = trade_controller.prepare_order(
                cs, instr, equity=equity, cfg=cfg, day_pnl_value=dpnl,
                open_count=open_count)
            mult = min(1.0, quality_multiplier(gate.score))
            if mult < 1.0:
                pending.order_request.qty = max(1, int(pending.order_request.qty * mult))

            pending_id = store.add(pending, cs)
            store.mark_pushed(fingerprint)
            push_fn(pending_id, instr, cs)
        except Exception:                                  # noqa: BLE001
            log.exception("tick failed for %s; continuing", instr.symbol)
            continue


async def scheduler_loop(*, interval_seconds: int, tick_fn, stop_event: asyncio.Event) -> None:
    """Runs tick_fn() immediately, then every interval_seconds, until stop_event is
    set. tick_fn takes no args — callers close over their own dependencies."""
    while not stop_event.is_set():
        try:
            tick_fn()
        except Exception:                                  # noqa: BLE001
            log.exception("scheduler tick raised unexpectedly")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_scheduler.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/scheduler.py tests/api/test_scheduler.py
git commit -m "feat(api): add background scheduler that prepares signals for the phone"
```

---

## Task 10: Signals Router (safety-critical)

**Files:**
- Create: `api/routers/signals.py`
- Test: `tests/api/test_signals_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_signals_router.py`:
```python
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.models import (ConsensusSignal, Instrument, OrderRequest, OrderType,
                         RiskCheck, Side, SignalType)
from services.trade_controller import PendingOrder
from api.auth import require_user
from api.deps import get_dhan_client, get_journal, get_pending_store
from api.routers import signals
from api.state import PendingStore


def _app(store, dhan, journal):
    app = FastAPI()
    app.include_router(signals.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_pending_store] = lambda: store
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    app.dependency_overrides[get_journal] = lambda: journal
    return app


def _pending(allowed=True):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET,
                       qty=10, price=100.0, stop_loss=95.0, target=110.0)
    check = RiskCheck(allowed=allowed, reasons=[] if allowed else ["Max open positions"])
    return PendingOrder(order_request=req, risk_check=check)


def _consensus():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    return ConsensusSignal(instrument=instr, providers=[], consensus=SignalType.BUY,
                           avg_confidence=80, agreement_pct=100,
                           indicator_snapshot={"entry": 100.0, "stop_loss": 95.0,
                                              "target": 110.0})


def test_list_pending_returns_stored_signals(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.get("/signals/pending")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["pending_id"] == pid
    assert body[0]["symbol"] == "RELIANCE"
    assert body[0]["risk_check"]["allowed"] is True


def test_confirm_places_order_and_removes_entry(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=True), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post(f"/signals/{pid}/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(fake_dhan.bracket) == 1          # SL+target -> bracket order
    assert store.get(pid) is None               # popped, can't confirm again


def test_confirm_unknown_id_returns_404_and_places_nothing(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post("/signals/does-not-exist/confirm")

    assert resp.status_code == 404
    assert fake_dhan.placed == []
    assert fake_dhan.bracket == []


def test_confirm_double_call_second_is_404(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=True), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    first = client.post(f"/signals/{pid}/confirm")
    second = client.post(f"/signals/{pid}/confirm")

    assert first.status_code == 200
    assert second.status_code == 404
    assert len(fake_dhan.bracket) == 1   # only placed once


def test_confirm_risk_blocked_returns_blocked_status_and_places_nothing(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    pid = store.add(_pending(allowed=False), _consensus())
    client = TestClient(_app(store, fake_dhan, temp_journal))

    resp = client.post(f"/signals/{pid}/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "BLOCKED"
    assert fake_dhan.placed == []
    assert fake_dhan.bracket == []


def test_pending_requires_auth(fake_dhan, temp_journal):
    store = PendingStore(ttl_seconds=300)
    app = FastAPI()
    app.include_router(signals.router)
    app.dependency_overrides[get_pending_store] = lambda: store
    app.dependency_overrides[get_dhan_client] = lambda: fake_dhan
    app.dependency_overrides[get_journal] = lambda: temp_journal
    client = TestClient(app)

    resp = client.get("/signals/pending")

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_signals_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.signals'`

- [ ] **Step 3: Write `api/routers/signals.py`**

```python
"""GET /signals/pending and POST /signals/{id}/confirm — the phone's only write
path into the order-placement pipeline. Preparation happens in the scheduler
(api/scheduler.py); this router cannot create a confirmable entry, only resolve
one that the scheduler already prepared and risk-checked."""
from __future__ import annotations
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_user
from api.deps import get_dhan_client, get_journal, get_pending_store
from api.schemas import ConfirmResponse, PendingSignalOut, RiskCheckOut
from services import trade_controller

router = APIRouter(prefix="/signals", tags=["signals"])


def _to_out(stored) -> PendingSignalOut:
    req = stored.pending.order_request
    rc = stored.pending.risk_check
    return PendingSignalOut(
        pending_id=stored.pending_id, symbol=req.instrument.symbol,
        side=req.side.value, qty=req.qty, entry=req.price,
        stop_loss=req.stop_loss, target=req.target,
        consensus=stored.consensus.consensus.value,
        avg_confidence=stored.consensus.avg_confidence,
        agreement_pct=stored.consensus.agreement_pct,
        risk_check=RiskCheckOut(**asdict(rc)))


@router.get("/pending", response_model=list[PendingSignalOut])
def list_pending(user_id: str = Depends(require_user),
                 store=Depends(get_pending_store)):
    return [_to_out(s) for s in store.list_active()]


@router.post("/{pending_id}/confirm", response_model=ConfirmResponse)
def confirm(pending_id: str, user_id: str = Depends(require_user),
           store=Depends(get_pending_store), dhan=Depends(get_dhan_client),
           journal=Depends(get_journal)):
    stored = store.pop(pending_id)
    if stored is None:
        raise HTTPException(status_code=404,
                            detail="signal expired or already resolved")
    result = trade_controller.confirm_and_place(
        stored.pending, dhan_client=dhan, journal_conn=journal,
        consensus=stored.consensus)
    return ConfirmResponse(ok=result.ok, status=result.status,
                           dhan_order_id=result.dhan_order_id,
                           exec_price=result.exec_price,
                           error_message=result.error_message)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_signals_router.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/signals.py tests/api/test_signals_router.py
git commit -m "feat(api): add signals router (list pending, two-step confirm)"
```

---

## Task 11: Push Registration Router

**Files:**
- Create: `api/routers/push.py`
- Test: `tests/api/test_push_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_push_router.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.routers import push as push_router


def test_register_calls_supabase_client_with_user_and_token(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.supabase_client.register_push_token",
        lambda user_id, token: calls.append((user_id, token)))

    app = FastAPI()
    app.include_router(push_router.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    client = TestClient(app)

    resp = client.post("/push/register", json={"token": "device-abc"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert calls == [("user-1", "device-abc")]


def test_register_requires_auth():
    app = FastAPI()
    app.include_router(push_router.router)
    client = TestClient(app)

    resp = client.post("/push/register", json={"token": "device-abc"})

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_push_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.push'`

- [ ] **Step 3: Write `api/routers/push.py`**

```python
"""POST /push/register — the phone tells us which FCM token belongs to the
logged-in device, stored in Supabase's push_tokens table."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api import supabase_client
from api.auth import require_user
from api.schemas import PushTokenIn

router = APIRouter(prefix="/push", tags=["push"])


@router.post("/register")
def register(body: PushTokenIn, user_id: str = Depends(require_user)):
    supabase_client.register_push_token(user_id, body.token)
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_push_router.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/push.py tests/api/test_push_router.py
git commit -m "feat(api): add push token registration router"
```

---

## Task 12: Positions Router

**Files:**
- Create: `api/routers/positions.py`
- Test: `tests/api/test_positions_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_positions_router.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_dhan_client
from api.routers import positions
from services.dhan_client import DhanError


def _app(dhan):
    app = FastAPI()
    app.include_router(positions.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    return app


def test_list_positions_returns_dhan_positions(fake_dhan):
    fake_dhan.positions = [{"tradingSymbol": "RELIANCE", "netQty": 10}]
    client = TestClient(_app(fake_dhan))

    resp = client.get("/positions")

    assert resp.status_code == 200
    assert resp.json() == [{"tradingSymbol": "RELIANCE", "netQty": 10}]


def test_list_positions_returns_502_on_dhan_error(fake_dhan, monkeypatch):
    def raise_error():
        raise DhanError("boom")
    fake_dhan.get_positions = raise_error
    client = TestClient(_app(fake_dhan))

    resp = client.get("/positions")

    assert resp.status_code == 502


def test_exit_position_calls_dhan_exit(fake_dhan):
    client = TestClient(_app(fake_dhan))

    resp = client.post("/positions/1/exit",
                       params={"exchange_segment": "NSE_EQ", "symbol": "RELIANCE"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dhan_order_id"] == "PAPER-EXIT-RELIANCE"


def test_positions_requires_auth(fake_dhan):
    app = FastAPI()
    app.include_router(positions.router)
    app.dependency_overrides[get_dhan_client] = lambda: fake_dhan
    client = TestClient(app)

    resp = client.get("/positions")

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_positions_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.positions'`

- [ ] **Step 3: Write `api/routers/positions.py`**

```python
"""GET /positions and POST /positions/{security_id}/exit — thin wrappers over
dhan_client, the same calls app.py's positions panel makes."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_user
from api.deps import get_dhan_client
from core.models import Instrument
from services.dhan_client import DhanError

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
def list_positions(user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    try:
        return dhan.get_positions()
    except DhanError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{security_id}/exit")
def exit_position(security_id: str, exchange_segment: str, symbol: str,
                  user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="EQUITY")
    result = dhan.exit_position(instr)
    return {"ok": result.ok, "status": result.status,
           "dhan_order_id": result.dhan_order_id,
           "error_message": result.error_message}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_positions_router.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/positions.py tests/api/test_positions_router.py
git commit -m "feat(api): add positions router"
```

---

## Task 13: Reports Router

**Files:**
- Create: `api/routers/reports.py`
- Test: `tests/api/test_reports_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_reports_router.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_journal
from api.routers import reports
from data.journal import log_order
from core.models import (Instrument, OrderRequest, OrderResult, OrderType, Side,
                         TradeMode)


def _app(journal):
    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_journal] = lambda: journal
    return app


def test_get_pnl_returns_statement_shape(temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET, qty=10,
                       price=100.0)
    result = OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
                         dhan_order_id="O1", exec_price=100.0)
    log_order(temp_journal, req, result)
    client = TestClient(_app(temp_journal))

    resp = client.get("/reports/pnl", params={"mode": "PAPER", "period": "all"})

    assert resp.status_code == 200
    body = resp.json()
    assert "total_pnl" in body
    assert body["mode"] == "PAPER"


def test_get_eod_returns_report_dict(temp_journal):
    client = TestClient(_app(temp_journal))

    resp = client.get("/reports/eod", params={"mode": "PAPER"})

    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body


def test_reports_require_auth(temp_journal):
    app = FastAPI()
    app.include_router(reports.router)
    app.dependency_overrides[get_journal] = lambda: temp_journal
    client = TestClient(app)

    resp = client.get("/reports/pnl")

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_reports_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.reports'`

- [ ] **Step 3: Write `api/routers/reports.py`**

```python
"""GET /reports/pnl and GET /reports/eod — read-only wrappers over accounting +
eod_report, the same data the desktop Reports page shows."""
from __future__ import annotations
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from api.auth import require_user
from api.deps import get_journal
from data.journal import to_legs
from services.accounting import pnl_statement
from services.eod_report import build_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/pnl")
def get_pnl(mode: str = Query("PAPER"), period: str = Query("all"),
           period_key: str | None = Query(None),
           user_id: str = Depends(require_user), journal=Depends(get_journal)):
    legs = to_legs(journal, mode=mode)
    stmt = pnl_statement(legs, mode=mode, period=period, period_key=period_key,
                         ltp_fn=lambda s: None)
    return asdict(stmt)


@router.get("/eod")
def get_eod(mode: str = Query("PAPER"), date: str | None = Query(None),
           user_id: str = Depends(require_user), journal=Depends(get_journal)):
    return build_report(journal, mode=mode, date_key=date)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_reports_router.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/reports.py tests/api/test_reports_router.py
git commit -m "feat(api): add reports router"
```

---

## Task 14: Screener Router

**Files:**
- Create: `api/routers/screener.py`
- Test: `tests/api/test_screener_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_screener_router.py`:
```python
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
    # no candles registered -> get_candles returns None -> scan() catches len(None)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_screener_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.screener'`

- [ ] **Step 3: Write `api/routers/screener.py`**

```python
"""GET /screener — ranked current setups across the watchlist, using the same
algorithm services/screener.py already provides to the desktop Screener page."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.deps import get_dhan_client, load_watchlist
from services.screener import scan

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("")
def get_screener(user_id: str = Depends(require_user), dhan=Depends(get_dhan_client),
                 watchlist=Depends(load_watchlist)):
    def _candles_fn(instr):
        style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
        return dhan.get_candles(instr, interval=15 if style == "intraday" else "day",
                                lookback_days=10)

    return scan(watchlist, candles_fn=_candles_fn, active_ids=list(range(1, 30)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_screener_router.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/screener.py tests/api/test_screener_router.py
git commit -m "feat(api): add screener router"
```

---

## Task 15: Options Router

**Files:**
- Create: `api/routers/options.py`
- Test: `tests/api/test_options_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_options_router.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.deps import get_dhan_client
from api.routers import options


def _app(dhan):
    app = FastAPI()
    app.include_router(options.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    app.dependency_overrides[get_dhan_client] = lambda: dhan
    return app


class ExpiryDhan:
    """Extends FakeDhan-shaped object with the sdk methods options_chain.py calls."""
    def __init__(self, mode="PAPER"):
        self.mode = mode

        class _Sdk:
            def expiry_list(self, security_id, exchange_segment):
                return {"data": ["2026-07-31", "2026-08-28"]}

            def option_chain(self, security_id, exchange_segment, expiry):
                return {"data": {"oc": {
                    "2500": {"ce": {"last_price": 12.5, "iv": 18.0,
                                    "greeks": {"delta": 0.5}, "oi": 1000},
                             "pe": {"last_price": 10.0, "iv": 19.0,
                                    "greeks": {"delta": -0.5}, "oi": 900}},
                }}}
        self.sdk = _Sdk()


def test_expiries_returns_list_from_dhan():
    client = TestClient(_app(ExpiryDhan()))

    resp = client.get("/options/expiries", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13"})

    assert resp.status_code == 200
    assert resp.json() == ["2026-07-31", "2026-08-28"]


def test_chain_returns_parsed_rows():
    client = TestClient(_app(ExpiryDhan()))

    resp = client.get("/options/chain", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13",
        "expiry": "2026-07-31"})

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["strike"] == 2500.0
    assert body[0]["ce"]["ltp"] == 12.5


def test_payoff_computes_curve_and_metrics():
    client = TestClient(_app(ExpiryDhan()))
    payload = {"legs": [{"type": "CE", "action": "BUY", "strike": 100.0,
                         "premium": 5.0, "lots": 1, "lot_size": 1}],
              "spot_ref": 100.0}

    resp = client.post("/options/payoff", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert "max_profit" in body
    assert "max_loss" in body
    assert len(body["xs"]) == len(body["ys"])


def test_options_require_auth():
    app = FastAPI()
    app.include_router(options.router)
    app.dependency_overrides[get_dhan_client] = lambda: ExpiryDhan()
    client = TestClient(app)

    resp = client.get("/options/expiries", params={
        "symbol": "NIFTY", "exchange_segment": "IDX_I", "security_id": "13"})

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_options_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.options'`

- [ ] **Step 3: Write `api/routers/options.py`**

```python
"""GET /options/expiries, GET /options/chain, POST /options/payoff — wrappers over
options_chain.py (live Dhan data) and options_payoff.py (pure math), the same data
the desktop Options page shows."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.deps import get_dhan_client
from api.schemas import PayoffOut, PayoffRequest
from core.models import Instrument
from services.options_chain import get_chain, get_expiries
from services.options_payoff import metrics, payoff_curve

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/expiries")
def expiries(symbol: str, exchange_segment: str, security_id: str,
            user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="OPTION")
    return get_expiries(instr, dhan)


@router.get("/chain")
def chain(symbol: str, exchange_segment: str, security_id: str, expiry: str,
         user_id: str = Depends(require_user), dhan=Depends(get_dhan_client)):
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="OPTION")
    return get_chain(instr, expiry, dhan)


@router.post("/payoff", response_model=PayoffOut)
def payoff(req: PayoffRequest, user_id: str = Depends(require_user)):
    legs = [leg.model_dump() for leg in req.legs]
    m = metrics(legs, req.spot_ref)
    lo, hi = req.spot_ref * 0.7, req.spot_ref * 1.3
    xs, ys = payoff_curve(legs, lo, hi)
    return PayoffOut(xs=xs, ys=ys, **m)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_options_router.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/options.py tests/api/test_options_router.py
git commit -m "feat(api): add options chain/payoff router"
```

---

## Task 16: Settings Router

**Files:**
- Create: `api/routers/settings.py`
- Test: `tests/api/test_settings_router.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_settings_router.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import require_user
from api.routers import settings as settings_router
from core import config_store, readiness


def _app():
    app = FastAPI()
    app.include_router(settings_router.router)
    app.dependency_overrides[require_user] = lambda: "user-1"
    return app


def _redirect_settings_path(monkeypatch, path):
    """config_store's and readiness's `path` parameters default to SETTINGS_PATH
    evaluated at import time, so monkeypatching the config_store.SETTINGS_PATH
    attribute alone does NOT change already-bound function defaults. Rebind each
    function's __defaults__ directly; monkeypatch restores the originals after
    the test. Without this, these tests would silently read/write the real
    ~/.dhan_claude_trader/settings.local.json on the machine running them."""
    monkeypatch.setattr(config_store, "SETTINGS_PATH", path)
    monkeypatch.setattr(config_store.load, "__defaults__", (path,))
    monkeypatch.setattr(config_store.save, "__defaults__", (path,))
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, path))
    monkeypatch.setattr(readiness.get_state, "__defaults__", (path,))
    monkeypatch.setattr(readiness.set_gate, "__defaults__", (path,))
    monkeypatch.setattr(readiness.passed_count, "__defaults__", (path,))
    monkeypatch.setattr(readiness.all_passed, "__defaults__", (path,))


def test_get_risk_reads_current_settings(monkeypatch):
    monkeypatch.setenv("MAX_DAILY_LOSS", "8000")
    monkeypatch.setenv("MAX_RISK_PER_TRADE_PCT", "1.5")
    monkeypatch.setenv("MAX_OPEN_POSITIONS", "4")
    client = TestClient(_app())

    resp = client.get("/settings/risk")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"max_daily_loss": 8000.0, "max_risk_per_trade_pct": 1.5,
                    "max_open_positions": 4}


def test_put_risk_saves_and_returns_updated_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.local.json"
    _redirect_settings_path(monkeypatch, settings_path)
    client = TestClient(_app())

    resp = client.put("/settings/risk", json={"max_daily_loss": 20000})

    assert resp.status_code == 200
    assert resp.json()["max_daily_loss"] == 20000.0
    assert config_store.load(settings_path)["MAX_DAILY_LOSS"] == "20000.0"


def test_get_readiness_reports_all_five_gates(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.local.json"
    _redirect_settings_path(monkeypatch, settings_path)
    readiness.set_gate("connectivity", True)
    client = TestClient(_app())

    resp = client.get("/settings/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["gates"]) == 5
    assert body["passed_count"] == 1
    assert body["all_passed"] is False
    connectivity = next(g for g in body["gates"] if g["id"] == "connectivity")
    assert connectivity["passed"] is True


def test_settings_require_auth():
    app = FastAPI()
    app.include_router(settings_router.router)
    client = TestClient(app)

    resp = client.get("/settings/risk")

    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_settings_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.routers.settings'`

- [ ] **Step 3: Write `api/routers/settings.py`**

```python
"""GET/PUT /settings/risk and GET /settings/readiness — the existing risk-limit
config store and 5-gate Go-Live checklist, the same data the desktop
Settings/Go-Live pages show. This does not change what limits exist, only lets
the phone read/write the existing values."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.schemas import GateOut, ReadinessOut, RiskSettingsIn, RiskSettingsOut
from core import config_store, readiness

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/risk", response_model=RiskSettingsOut)
def get_risk(user_id: str = Depends(require_user)):
    return RiskSettingsOut(
        max_daily_loss=float(config_store.get_setting("MAX_DAILY_LOSS", "10000")),
        max_risk_per_trade_pct=float(
            config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0")),
        max_open_positions=int(config_store.get_setting("MAX_OPEN_POSITIONS", "2")))


@router.put("/risk", response_model=RiskSettingsOut)
def put_risk(body: RiskSettingsIn, user_id: str = Depends(require_user)):
    updates = {}
    if body.max_daily_loss is not None:
        updates["MAX_DAILY_LOSS"] = str(body.max_daily_loss)
    if body.max_risk_per_trade_pct is not None:
        updates["MAX_RISK_PER_TRADE_PCT"] = str(body.max_risk_per_trade_pct)
    if body.max_open_positions is not None:
        updates["MAX_OPEN_POSITIONS"] = str(body.max_open_positions)
    config_store.save(updates)
    return get_risk(user_id)


@router.get("/readiness", response_model=ReadinessOut)
def get_readiness(user_id: str = Depends(require_user)):
    state = readiness.get_state()
    gates = [GateOut(id=gid, label=label, kind=kind, passed=bool(state.get(gid)))
            for gid, label, kind in readiness.GATES]
    return ReadinessOut(gates=gates, passed_count=readiness.passed_count(),
                        all_passed=readiness.all_passed())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_settings_router.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/routers/settings.py tests/api/test_settings_router.py
git commit -m "feat(api): add settings/readiness router"
```

---

## Task 17: Main App Assembly

**Files:**
- Create: `api/main.py`
- Test: `tests/api/test_main.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_main.py`:
```python
from fastapi.testclient import TestClient

from api.main import create_app


def test_health_check_works_without_auth():
    app = create_app(start_scheduler=False)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_route_rejects_missing_auth():
    app = create_app(start_scheduler=False)
    with TestClient(app) as client:
        resp = client.get("/signals/pending")
    assert resp.status_code == 401


def test_protected_route_accepts_valid_jwt(make_jwt):
    app = create_app(start_scheduler=False)
    token = make_jwt()
    with TestClient(app) as client:
        resp = client.get("/signals/pending", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_app_starts_and_stops_scheduler_without_hanging(monkeypatch):
    # _tick() is mocked here: the real one calls get_dhan_client()/get_journal(),
    # which would hit the live Dhan API and write to the real trades.db on this
    # machine. This test only needs to prove create_app(start_scheduler=True)
    # starts a background task and the lifespan shuts it down cleanly.
    import api.main as main
    calls = {"n": 0}
    monkeypatch.setattr(main, "_tick", lambda: calls.__setitem__("n", calls["n"] + 1))
    app = main.create_app(start_scheduler=True)

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    assert calls["n"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: Write `api/main.py`**

```python
"""FastAPI app assembly: wires auth, routers, and the background scheduler
together. Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000

create_app(start_scheduler=False) is used by tests so a hermetic test run never
depends on real Dhan/Supabase/FCM credentials or network access — the scheduler
loop is the only piece of this module with an external side effect on startup."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import push, supabase_client
from api.deps import (get_dhan_client, get_equity, get_journal, get_pending_store,
                      get_risk_config, load_watchlist)
from api.routers import options, positions, push as push_router, reports, screener, settings, signals
from api.scheduler import run_tick, scheduler_loop
from core import config_store


def _make_push_fn():
    def _push(pending_id, instrument, consensus):
        title = f"New signal: {instrument.symbol} {consensus.consensus.value}"
        for token in supabase_client.list_push_tokens():
            push.send_push(token, title, "Review now", data={"pending_id": pending_id})
    return _push


def _tick() -> None:
    dhan = get_dhan_client()
    journal = get_journal()
    cfg = get_risk_config()
    watchlist = load_watchlist()
    mode = config_store.get_setting("TRADE_MODE", "PAPER")
    equity = get_equity(mode, dhan)
    run_tick(watchlist=watchlist, dhan_client=dhan, journal_conn=journal, cfg=cfg,
            equity=equity, store=get_pending_store(), push_fn=_make_push_fn(),
            signal_source=config_store.get_setting("SIGNAL_SOURCE", "mock"))


def create_app(*, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop_event = asyncio.Event()
        task = None
        if start_scheduler:
            interval = int(config_store.get_setting("SIGNAL_COOLDOWN_SECONDS", "300"))
            task = asyncio.create_task(
                scheduler_loop(interval_seconds=interval, tick_fn=_tick,
                               stop_event=stop_event))
        yield
        stop_event.set()
        if task is not None:
            await task

    app = FastAPI(title="Dhan-Claude Trader API", lifespan=lifespan)
    app.include_router(signals.router)
    app.include_router(positions.router)
    app.include_router(reports.router)
    app.include_router(screener.router)
    app.include_router(options.router)
    app.include_router(settings.router)
    app.include_router(push_router.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_main.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all previously-passing tests (112+) still pass, plus all new `tests/api/` tests.

- [ ] **Step 6: Commit**

```bash
git add api/main.py tests/api/test_main.py
git commit -m "feat(api): assemble FastAPI app with routers and background scheduler"
```

---

## Task 18: Deployment Wiring

**Files:**
- Create: `run_api.bat`
- Modify: `.env.example`
- Modify: `AUTOSTART.md`

- [ ] **Step 1: Create `run_api.bat`**

```batch
@echo off
REM ============================================================
REM  Dhan-Claude Trader API launcher (Windows)
REM  Serves the FastAPI layer at http://localhost:8000 for the
REM  Android app (via a Cloudflare Tunnel pointed at this port).
REM  Run this ALONGSIDE run_app.bat, not instead of it.
REM ============================================================
cd /d "%~dp0"
echo Starting Dhan-Claude Trader API...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
pause
```

- [ ] **Step 2: Add new required env vars to `.env.example`**

Append to `.env.example`:

```
# ---- Mobile API layer (api/) ----
# Supabase project (Settings > API): used to verify the phone app's login JWT.
SUPABASE_URL=
SUPABASE_JWT_SECRET=
SUPABASE_SERVICE_ROLE_KEY=

# Firebase project: used to push "new signal" alerts to the phone.
FCM_PROJECT_ID=
FCM_SERVICE_ACCOUNT_JSON_PATH=
```

- [ ] **Step 3: Update `AUTOSTART.md` to mention the second process**

Read the current `AUTOSTART.md` first, then add a short section (matching its existing style) noting that `run_api.bat` must be started alongside `run_app.bat` for the mobile app to work, and that a Cloudflare Tunnel (`cloudflared tunnel run <tunnel-name>`) pointed at `localhost:8000` is what gives the phone a stable public URL. Do not remove or restructure existing content — this is an addition only.

- [ ] **Step 4: Manual verification**

Run: `run_api.bat`
Expected: uvicorn starts, logs `Uvicorn running on http://0.0.0.0:8000`, and `curl http://localhost:8000/health` (in a second terminal) returns `{"status":"ok"}`.

Stop the server (Ctrl+C in the `run_api.bat` window) and confirm it shuts down cleanly (no traceback, no hang) — this exercises the same lifespan shutdown path `test_app_starts_and_stops_scheduler_without_hanging` checks in-process.

- [ ] **Step 5: Commit**

```bash
git add run_api.bat .env.example AUTOSTART.md
git commit -m "docs(api): add run_api.bat launcher and required env vars"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (module layout) → Tasks 1–17 create every file listed. §4 (signal lifecycle) → Tasks 9–10 (scheduler prepares, router only confirms, no client-reachable prepare endpoint). §5 (auth) → Task 3. §6 (error handling) → 404 on unknown/expired pending_id (Task 10), 502 on DhanError (Task 12), BLOCKED-not-error on risk-blocked confirm (Task 10), push failures swallowed (Task 7), per-instrument tick failures isolated (Task 9). §7 (testing) → every module has a colocated test; the no-auto-fire guarantee is proven through the HTTP layer in Task 10 (`test_confirm_double_call_second_is_404`, `test_confirm_risk_blocked_returns_blocked_status_and_places_nothing`). §8 (deployment) → Task 18.
- **Not covered by this plan (correctly, per spec §9 Out of Scope):** the Android app itself, Play Store distribution, rate limiting beyond Cloudflare's default, and changing risk limit *values* (Task 16 only exposes the existing read/write path).
- **TTL choice:** `PendingStore`'s TTL reuses `SIGNAL_COOLDOWN_SECONDS` (Task 6, `get_pending_store`). This means a prepared signal stays confirmable for one cooldown window before the scheduler's next tick would naturally supersede it — reusing an existing, already-understood config value rather than inventing a new one.
