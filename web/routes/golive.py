"""Go-Live page — the 5 readiness gates from core.readiness."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core import readiness
from web.server import templates

router = APIRouter()


def _ctx(request):
    state = readiness.get_state()
    gates = [{"id": g, "label": l, "kind": k, "passed": bool(state.get(g))}
             for g, l, k in readiness.GATES]
    return {"request": request, "gates": gates, "passed": readiness.passed_count(),
            "all": readiness.all_passed(), "total": len(readiness.GATE_IDS)}


@router.get("/golive", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse("golive.html", _ctx(request))


@router.post("/golive/gate", response_class=HTMLResponse)
def toggle(request: Request, gate_id: str = Form(...), value: str = Form("true")):
    readiness.set_gate(gate_id, value == "true")
    return templates.TemplateResponse("golive.html", _ctx(request))
