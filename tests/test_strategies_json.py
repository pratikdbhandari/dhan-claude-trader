import json
from pathlib import Path


def test_presets_reference_valid_ids():
    data = json.loads(Path("strategies.json").read_text())
    valid = {s["id"] for s in data["strategies"]}
    assert len(valid) == 29
    for name, ids in data["presets"].items():
        assert set(ids).issubset(valid), f"{name} references unknown id"
