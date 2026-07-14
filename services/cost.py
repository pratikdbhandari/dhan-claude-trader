"""Per-run AI cost tracking. Pure pricing math + a best-effort JSONL ledger of every
AI call's token usage and INR cost. Never raises (a cost-log failure must not block
signal generation). Path/prices resolve from module globals so they stay patchable."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

COST_PATH = "cost.jsonl"
COSTS_PATH = "costs.json"


def load_prices(path=None) -> dict:
    path = path if path is not None else COSTS_PATH
    try:
        p = Path(path)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                              # noqa: BLE001
        log.exception("cost load_prices failed")
        return {}


def run_cost(model: str, in_tok: int, out_tok: int, prices: dict) -> float:
    row = prices.get(model) or prices.get("default") or {}
    c = (in_tok / 1000.0) * float(row.get("input_per_1k", 0.0)) \
        + (out_tok / 1000.0) * float(row.get("output_per_1k", 0.0))
    return round(c, 4)


def log_run(model: str, in_tok: int, out_tok: int, *, path=None, prices=None) -> None:
    path = path if path is not None else COST_PATH
    try:
        prices = prices if prices is not None else load_prices()
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "model": model, "in": int(in_tok), "out": int(out_tok),
                           "cost": run_cost(model, in_tok, out_tok, prices)})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                              # noqa: BLE001 - never block signals
        log.exception("cost log_run failed")


def read_runs(path=None, limit: int = 500) -> list[dict]:
    path = path if path is not None else COST_PATH
    try:
        p = Path(path)
        if not p.exists():
            return []
        out = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return list(reversed(out))[:limit]
    except Exception:                              # noqa: BLE001
        log.exception("cost read_runs failed")
        return []


def summary(runs: list[dict], period: str = "all", now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()

    def _in_period(ts: str) -> bool:
        if period == "all":
            return True
        try:
            d = datetime.fromisoformat(ts).astimezone(now.tzinfo or timezone.utc).date()
        except (ValueError, TypeError):
            return False
        if period == "day":
            return d == today
        if period == "month":
            return d.year == today.year and d.month == today.month
        return True

    sel = [r for r in runs if _in_period(r.get("ts", ""))]
    by_model: dict[str, dict] = {}
    for r in sel:
        m = r.get("model", "?")
        b = by_model.setdefault(m, {"cost": 0.0, "in": 0, "out": 0, "n": 0})
        b["cost"] = round(b["cost"] + float(r.get("cost", 0)), 4)
        b["in"] += int(r.get("in", 0))
        b["out"] += int(r.get("out", 0))
        b["n"] += 1
    return {"total_cost": round(sum(r.get("cost", 0) for r in sel), 4),
            "total_in": sum(int(r.get("in", 0)) for r in sel),
            "total_out": sum(int(r.get("out", 0)) for r in sel),
            "n_runs": len(sel), "by_model": by_model}
