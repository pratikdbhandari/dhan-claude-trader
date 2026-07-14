from datetime import datetime, timezone, timedelta

from services import cost

IST = timezone(timedelta(hours=5, minutes=30))
_PRICES = {"default": {"input_per_1k": 0.0, "output_per_1k": 0.0},
           "m1": {"input_per_1k": 1.0, "output_per_1k": 2.0}}


def test_run_cost_listed_model():
    assert cost.run_cost("m1", 2000, 1000, _PRICES) == 4.0


def test_run_cost_unknown_model_uses_default():
    assert cost.run_cost("unknown", 5000, 5000, _PRICES) == 0.0


def test_load_prices_reads_file(tmp_path):
    import json
    p = tmp_path / "costs.json"
    p.write_text(json.dumps({"default": {"input_per_1k": 0, "output_per_1k": 0},
                             "m1": {"input_per_1k": 3.0, "output_per_1k": 6.0}}))
    prices = cost.load_prices(path=p)
    assert prices["m1"]["input_per_1k"] == 3.0


def test_load_prices_missing_file_returns_empty(tmp_path):
    assert cost.load_prices(path=tmp_path / "nope.json") == {}


def test_log_and_read_runs_roundtrip(tmp_path):
    p = tmp_path / "cost.jsonl"
    cost.log_run("m1", 1000, 500, path=p, prices=_PRICES)
    cost.log_run("m1", 2000, 1000, path=p, prices=_PRICES)
    runs = cost.read_runs(path=p, limit=10)
    assert len(runs) == 2
    assert runs[0]["in"] == 2000
    assert runs[0]["cost"] == 4.0
    assert "ts" in runs[0] and runs[0]["model"] == "m1"


def test_log_run_bad_path_swallowed():
    cost.log_run("m1", 1, 1, path="", prices=_PRICES)


def test_summary_aggregates_by_model_and_period():
    runs = [
        {"ts": "2026-07-14T10:00:00+05:30", "model": "m1", "in": 1000, "out": 500, "cost": 2.0},
        {"ts": "2026-07-14T11:00:00+05:30", "model": "m2", "in": 2000, "out": 0, "cost": 2.0},
        {"ts": "2026-06-01T10:00:00+05:30", "model": "m1", "in": 500, "out": 0, "cost": 0.5},
    ]
    now = datetime(2026, 7, 14, 15, 0, tzinfo=IST)
    day = cost.summary(runs, period="day", now=now)
    assert day["total_cost"] == 4.0 and day["total_in"] == 3000
    assert day["by_model"]["m1"]["cost"] == 2.0
    all_ = cost.summary(runs, period="all", now=now)
    assert all_["total_cost"] == 4.5 and all_["n_runs"] == 3


def test_summary_empty_zeros():
    s = cost.summary([], period="all")
    assert s["total_cost"] == 0.0 and s["n_runs"] == 0 and s["by_model"] == {}
