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
        # `app` identifies us specifically: run_web_hidden.vbs probes this before
        # opening a browser, and a bare {"status": "ok"} is answered by plenty of
        # other servers (Streamlit included) that could hold port 8501.
        return {"status": "ok", "app": "dhan-claude-trader"}

    from web.routes import (dashboard, live, analysis, reports, screener, backtest,
                            options, settings, golive, btst)
    for mod in (dashboard, live, analysis, reports, screener, backtest, options,
                settings, golive, btst):
        app.include_router(mod.router)
    return app


app = create_web_app()
