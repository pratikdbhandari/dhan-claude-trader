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
    monkeypatch.setattr(config_store, "SETTINGS_PATH", path)
    monkeypatch.setattr(config_store.load, "__defaults__", (path,))
    monkeypatch.setattr(config_store.save, "__defaults__", (path,))
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, path))
    monkeypatch.setattr(readiness.get_state, "__defaults__", (path,))
    monkeypatch.setattr(readiness.set_gate, "__defaults__", (path,))
    monkeypatch.setattr(readiness.passed_count, "__defaults__", (path,))
    monkeypatch.setattr(readiness.all_passed, "__defaults__", (path,))


def test_get_risk_reads_current_settings(monkeypatch, tmp_path):
    # isolate from the real settings.local.json (file wins over env in get_setting)
    _redirect_settings_path(monkeypatch, tmp_path / "empty.json")
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
