"""HTML web app: Jinja2 templates + htmx on FastAPI. Serves the same trading UI as
Streamlit, calling the same services. create_web_app() is import-safe and testable."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def create_web_app() -> FastAPI:
    app = FastAPI(title="Dhan-Claude Trader (HTML)")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from web.routes import dashboard, reports, screener
    for mod in (dashboard, reports, screener):
        app.include_router(mod.router)
    return app


app = create_web_app()
