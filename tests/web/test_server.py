from fastapi.testclient import TestClient
from web.server import create_web_app


def test_health_ok():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_static_css_served():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/static/app.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_static_htmx_served():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/static/htmx.min.js")
    assert r.status_code == 200
