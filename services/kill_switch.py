"""Global trading kill-switch. Halt state persists in config_store (survives
restart — a crash mid-halt comes back frozen, never accidentally live). The halt is
enforced structurally inside trade_controller.confirm_and_place, not just the UI."""
from __future__ import annotations
from core import config_store
from services import audit


def is_halted() -> bool:
    return str(config_store.get_setting("KILL_SWITCH", "false")).lower() == "true"


def halt(reason: str = "") -> None:
    config_store.save({"KILL_SWITCH": "true"})
    audit.log_event("HALT", {"reason": reason})


def resume() -> None:
    config_store.save({"KILL_SWITCH": "false"})
    audit.log_event("RESUME", {})
