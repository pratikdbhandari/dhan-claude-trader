from core import config_store
from services import audit, kill_switch


def _isolate(monkeypatch, tmp_path):
    settings = tmp_path / "settings.local.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", settings)
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, settings))
    monkeypatch.setattr(config_store.save, "__defaults__", (settings,))
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def test_default_not_halted(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert kill_switch.is_halted() is False


def test_halt_then_resume(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    kill_switch.halt("manual test")
    assert kill_switch.is_halted() is True
    kill_switch.resume()
    assert kill_switch.is_halted() is False


def test_halt_writes_audit_event(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    kill_switch.halt("panic")
    events = audit.read_events(path=str(tmp_path / "audit.jsonl"))
    assert any(e["event"] == "HALT" for e in events)


def test_kill_switch_key_registered():
    assert "KILL_SWITCH" in config_store.KEYS
