from fastapi.testclient import TestClient
from web.server import create_web_app


def test_health_ok():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    # the `app` field is load-bearing: the silent launcher uses it to tell our
    # server apart from anything else squatting on port 8501
    assert r.json() == {"status": "ok", "app": "dhan-claude-trader"}


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
