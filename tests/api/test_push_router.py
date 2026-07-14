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
