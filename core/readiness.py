"""Go-Live readiness gates. LIVE trading stays locked until all five gates are
checked. State persists in the local settings file (under "READINESS"), separate
from Git. Pure/injectable via path for tests."""
from __future__ import annotations
from core import config_store

# (id, label, kind) — kind 'auto' can be set by an in-app self-test, 'manual' by the user
GATES = [
    ("data_api", "Dhan Data API (₹499/mo) subscribed", "manual"),
    ("connectivity", "Live connectivity self-test passed (read-only)", "auto"),
    ("backtest", "Out-of-sample edge confirmed in backtest", "manual"),
    ("tiny_order", "One tiny LIVE order verified end-to-end", "manual"),
    ("paper_run", "15-day paper run completed", "manual"),
]
GATE_IDS = [g[0] for g in GATES]


def get_state(path=config_store.SETTINGS_PATH) -> dict:
    return config_store.load(path).get("READINESS", {})


def set_gate(gate_id: str, value: bool, path=config_store.SETTINGS_PATH) -> None:
    state = get_state(path)
    state[gate_id] = bool(value)
    config_store.save({"READINESS": state}, path)


def passed_count(path=config_store.SETTINGS_PATH) -> int:
    s = get_state(path)
    return sum(1 for gid in GATE_IDS if s.get(gid))


def all_passed(path=config_store.SETTINGS_PATH) -> bool:
    s = get_state(path)
    return all(s.get(gid) for gid in GATE_IDS)
