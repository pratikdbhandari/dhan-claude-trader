"""Append-only audit ledger (JSONL). One timestamped line per order-lifecycle event.
Best-effort: never raises, so an audit failure can never block or crash trading.
Path resolves from the AUDIT_PATH module global at call time so it stays patchable."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

AUDIT_PATH = "audit.jsonl"


def log_event(event: str, detail: dict | None = None, *, path=None) -> None:
    path = path if path is not None else AUDIT_PATH
    try:
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "event": event, "detail": detail or {}})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                              # noqa: BLE001 - never block trading
        log.exception("audit log_event failed")


def read_events(path=None, limit: int = 100) -> list[dict]:
    path = path if path is not None else AUDIT_PATH
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
        log.exception("audit read_events failed")
        return []
