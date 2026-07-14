from fastapi.testclient import TestClient
from web.server import create_web_app
import web.deps as wdeps
from core import config_store


def _client(monkeypatch, fake_dhan, temp_journal, tmp_path):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(config_store, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, tmp_path / "s.json"))
    monkeypatch.setattr(config_store.save, "__defaults__", (tmp_path / "s.json",))
    monkeypatch.setattr(config_store.load, "__defaults__", (tmp_path / "s.json",))
    from core import readiness
    for fn in ("get_state", "set_gate", "passed_count", "all_passed"):
        monkeypatch.setattr(getattr(readiness, fn), "__defaults__", (tmp_path / "s.json",))
    return TestClient(create_web_app())


def test_settings_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "Save settings" in c.get("/settings").text


def test_settings_save(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    r = c.post("/settings/save", data={"max_daily_loss": "5000"})
    assert "saved" in r.text.lower()
    assert config_store.load(tmp_path / "s.json")["MAX_DAILY_LOSS"] == "5000"


def test_golive_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "readiness" in c.get("/golive").text.lower()


def test_options_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert c.get("/options").status_code == 200


def test_btst_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "Buy Today" in c.get("/btst").text
