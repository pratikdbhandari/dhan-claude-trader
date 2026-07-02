import socket
from pathlib import Path

from desktop.launcher import (acquire_lock, find_free_port, release_lock,
                              resolve_user_dir, wait_for_health)


# ---------------------------------------------------------------- ports
def test_find_free_port_returns_bindable_port():
    port = find_free_port()
    # must be immediately bindable (the OS just released it)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))


def test_find_free_port_returns_ports_in_valid_range():
    ports = {find_free_port() for _ in range(5)}
    assert all(1024 < p < 65536 for p in ports)


# ---------------------------------------------------------------- health poll
def test_wait_for_health_true_when_endpoint_answers_ok():
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1

        class R:
            status_code = 200
            text = "ok"
        return R()

    assert wait_for_health("http://127.0.0.1:9999", timeout_s=5,
                           get_fn=fake_get, sleep_fn=lambda s: None) is True
    assert calls["n"] == 1


def test_wait_for_health_retries_then_succeeds():
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("not up yet")

        class R:
            status_code = 200
            text = "ok"
        return R()

    assert wait_for_health("http://127.0.0.1:9999", timeout_s=5,
                           get_fn=fake_get, sleep_fn=lambda s: None) is True
    assert calls["n"] == 3


def test_wait_for_health_false_on_timeout():
    clock = {"t": 0.0}

    def fake_sleep(s):
        clock["t"] += s

    def fake_get(url, timeout):
        raise ConnectionError("never up")

    assert wait_for_health("http://127.0.0.1:9999", timeout_s=2,
                           get_fn=fake_get, sleep_fn=fake_sleep,
                           now_fn=lambda: clock["t"]) is False


# ---------------------------------------------------------------- user dir
def test_resolve_user_dir_creates_data_dir_and_copies_defaults(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "watchlist.json").write_text('{"instruments": []}')
    (bundle / "strategies.json").write_text("{}")
    (bundle / "providers.json").write_text("{}")
    (bundle / "charges.json").write_text("{}")
    exe_dir = tmp_path / "install"
    exe_dir.mkdir()

    user_dir = resolve_user_dir(exe_dir=exe_dir, bundle_dir=bundle)

    assert user_dir == exe_dir / "data"
    assert user_dir.is_dir()
    assert (user_dir / "watchlist.json").read_text() == '{"instruments": []}'
    assert (user_dir / "reports").is_dir()


def test_resolve_user_dir_does_not_overwrite_existing_user_edits(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "watchlist.json").write_text('{"instruments": ["DEFAULT"]}')
    exe_dir = tmp_path / "install"
    (exe_dir / "data").mkdir(parents=True)
    (exe_dir / "data" / "watchlist.json").write_text('{"instruments": ["USER_EDIT"]}')

    user_dir = resolve_user_dir(exe_dir=exe_dir, bundle_dir=bundle)

    assert (user_dir / "watchlist.json").read_text() == '{"instruments": ["USER_EDIT"]}'


# ---------------------------------------------------------------- single instance
def test_acquire_lock_succeeds_then_blocks_second(tmp_path):
    lock = tmp_path / "app.lock"
    handle = acquire_lock(lock)
    assert handle is not None
    assert acquire_lock(lock) is None          # second instance blocked
    release_lock(handle, lock)
    assert acquire_lock(lock) is not None      # released -> acquirable again


def test_acquire_lock_recovers_from_stale_lockfile(tmp_path):
    lock = tmp_path / "app.lock"
    lock.write_text("999999")                  # dead PID, no process holds it
    handle = acquire_lock(lock)
    assert handle is not None


def test_release_lock_with_none_handle_does_not_delete_owners_lock(tmp_path):
    lock = tmp_path / "app.lock"
    owner = acquire_lock(lock)
    assert owner is not None
    denied = acquire_lock(lock)          # blocked -> None
    release_lock(denied, lock)           # must NOT delete the owner's lock
    assert lock.exists()
    release_lock(owner, lock)
    assert not lock.exists()


def test_acquire_lock_blocks_when_live_foreign_pid_holds_lock(tmp_path):
    import subprocess
    import sys
    lock = tmp_path / "app.lock"
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        lock.write_text(str(proc.pid))
        assert acquire_lock(lock) is None    # live foreign PID -> blocked
    finally:
        proc.kill()
        proc.wait()
