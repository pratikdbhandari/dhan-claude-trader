from core import config_store


def test_bell_keys_registered():
    assert "BELL_ENABLED" in config_store.KEYS
    assert "BELL_LEAD_MINUTES" in config_store.KEYS


def test_bell_settings_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    config_store.save({"BELL_ENABLED": "true", "BELL_LEAD_MINUTES": "15"}, path=p)
    assert config_store.get_setting("BELL_ENABLED", path=p) == "true"
    assert config_store.get_setting("BELL_LEAD_MINUTES", path=p) == "15"
