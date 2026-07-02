"""DhanTrader desktop launcher. Frozen by PyInstaller into DhanTrader.exe:
starts the existing Streamlit app headless on a free localhost port, waits for
its health endpoint, opens a native pywebview window, and shuts everything down
when the window closes. All functions above main() are pure/injectable and unit
tested; main() is verified manually via the packaged build."""
from __future__ import annotations
import os
import shutil
import socket
import sys
import time
from pathlib import Path

import requests

DEFAULT_CONFIGS = ("watchlist.json", "strategies.json", "providers.json", "charges.json")
HEALTH_TIMEOUT_S = 60


def find_free_port() -> int:
    """Bind port 0 (OS picks a free port), release it, return the number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(base_url: str, *, timeout_s: int = HEALTH_TIMEOUT_S,
                    get_fn=requests.get, sleep_fn=time.sleep,
                    now_fn=time.monotonic) -> bool:
    """Poll <base_url>/_stcore/health until it answers 200 'ok' or timeout."""
    deadline = now_fn() + timeout_s
    while now_fn() < deadline:
        try:
            r = get_fn(f"{base_url}/_stcore/health", timeout=2)
            if r.status_code == 200 and "ok" in r.text:
                return True
        except Exception:                              # noqa: BLE001 - server not up yet
            pass
        sleep_fn(0.25)
    return False


def resolve_user_dir(*, exe_dir: Path, bundle_dir: Path) -> Path:
    """Create <exe_dir>/data on first run and seed it with the bundled default
    config files. Never overwrites files the user already edited. trades.db,
    reports/ and the instrument-master cache all live here (the app opens them
    by relative path, so main() chdirs into this directory)."""
    user_dir = exe_dir / "data"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "reports").mkdir(exist_ok=True)
    for name in DEFAULT_CONFIGS:
        src = bundle_dir / name
        dst = user_dir / name
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)
    return user_dir


def _pid_alive(pid: int) -> bool:
    """Windows: os.kill(pid, 0) raises OSError if the PID doesn't exist."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def acquire_lock(lock_path: Path):
    """Single-instance guard. Returns an opaque handle on success, None if
    another live instance holds the lock. A lockfile whose PID is dead is stale
    (previous crash) and is taken over."""
    if lock_path.exists():
        try:
            other_pid = int(lock_path.read_text().strip())
        except ValueError:
            other_pid = None
        if other_pid is not None:
            if other_pid == os.getpid():
                return None  # We already hold this lock (in a prior call)
            if _pid_alive(other_pid):
                return None  # Another live process holds it
    lock_path.write_text(str(os.getpid()))
    return lock_path


def release_lock(handle, lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass
