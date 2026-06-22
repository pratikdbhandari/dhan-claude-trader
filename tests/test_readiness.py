from core import readiness


def test_starts_not_passed(tmp_path):
    p = tmp_path / "s.json"
    assert readiness.all_passed(p) is False
    assert readiness.passed_count(p) == 0


def test_set_gate_persists_and_counts(tmp_path):
    p = tmp_path / "s.json"
    readiness.set_gate("data_api", True, p)
    readiness.set_gate("connectivity", True, p)
    assert readiness.passed_count(p) == 2
    assert readiness.all_passed(p) is False


def test_all_gates_unlocks_live(tmp_path):
    p = tmp_path / "s.json"
    for gid in readiness.GATE_IDS:
        readiness.set_gate(gid, True, p)
    assert readiness.all_passed(p) is True


def test_unset_relocks(tmp_path):
    p = tmp_path / "s.json"
    for gid in readiness.GATE_IDS:
        readiness.set_gate(gid, True, p)
    readiness.set_gate("tiny_order", False, p)
    assert readiness.all_passed(p) is False
