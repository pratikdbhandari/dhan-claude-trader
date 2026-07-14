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
    import api.main as main
    calls = {"n": 0}
    monkeypatch.setattr(main, "_tick", lambda: calls.__setitem__("n", calls["n"] + 1))
    app = main.create_app(start_scheduler=True)

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    assert calls["n"] >= 1
