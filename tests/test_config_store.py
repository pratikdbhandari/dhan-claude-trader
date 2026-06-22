import os
from core import config_store


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "settings.local.json"
    config_store.save({"DHAN_CLIENT_ID": "abc", "TRADE_MODE": "PAPER"}, path=p)
    data = config_store.load(p)
    assert data["DHAN_CLIENT_ID"] == "abc" and data["TRADE_MODE"] == "PAPER"


def test_save_merges_not_wipes(tmp_path):
    p = tmp_path / "s.json"
    config_store.save({"DHAN_CLIENT_ID": "abc"}, path=p)
    config_store.save({"GROQ_API_KEY": "g"}, path=p)
    data = config_store.load(p)
    assert data["DHAN_CLIENT_ID"] == "abc" and data["GROQ_API_KEY"] == "g"


def test_get_setting_precedence(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    config_store.save({"DHAN_CLIENT_ID": "from_file"}, path=p)
    monkeypatch.setenv("DHAN_CLIENT_ID", "from_env")
    monkeypatch.setenv("GROQ_API_KEY", "env_only")
    # file wins over env
    assert config_store.get_setting("DHAN_CLIENT_ID", path=p) == "from_file"
    # env used when not in file
    assert config_store.get_setting("GROQ_API_KEY", path=p) == "env_only"
    # default when neither
    assert config_store.get_setting("MISSING", default="d", path=p) == "d"


def test_missing_file_returns_empty(tmp_path):
    assert config_store.load(tmp_path / "nope.json") == {}
