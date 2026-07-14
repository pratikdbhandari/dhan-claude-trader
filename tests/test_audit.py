from services import audit


def test_log_and_read_roundtrip_newest_first(tmp_path):
    p = tmp_path / "audit.jsonl"
    audit.log_event("PLACED", {"symbol": "RELIANCE"}, path=p)
    audit.log_event("HALT", {"reason": "manual"}, path=p)
    events = audit.read_events(path=p, limit=10)
    assert events[0]["event"] == "HALT"
    assert events[1]["event"] == "PLACED"
    assert events[0]["detail"]["reason"] == "manual"
    assert "ts" in events[0]


def test_read_respects_limit(tmp_path):
    p = tmp_path / "audit.jsonl"
    for i in range(5):
        audit.log_event("PREPARE", {"i": i}, path=p)
    assert len(audit.read_events(path=p, limit=2)) == 2


def test_read_missing_file_returns_empty(tmp_path):
    assert audit.read_events(path=tmp_path / "nope.jsonl") == []


def test_read_skips_malformed_lines(tmp_path):
    p = tmp_path / "audit.jsonl"
    audit.log_event("PLACED", {"ok": True}, path=p)
    with open(p, "a", encoding="utf-8") as f:
        f.write("not-json\n")
    events = audit.read_events(path=p)
    assert len(events) == 1 and events[0]["event"] == "PLACED"


def test_log_event_never_raises_on_bad_path():
    audit.log_event("X", {}, path="")     # no exception
