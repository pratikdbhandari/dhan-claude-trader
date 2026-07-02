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
    """True if PID exists. os.kill(pid, 0) is a pure existence probe here —
    verified on Python 3.13/Win11 (raises OSError for dead PIDs, does not
    terminate live ones), despite older docs suggesting otherwise."""
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
        except (ValueError, OSError):
            other_pid = None
        if other_pid is not None:
            if other_pid == os.getpid():
                return None  # We already hold this lock (in a prior call)
            if _pid_alive(other_pid):
                return None  # Another live process holds it
    lock_path.write_text(str(os.getpid()))
    return lock_path


def release_lock(handle, lock_path: Path) -> None:
    """Delete the lockfile, but only if we actually hold it — an instance whose
    acquire_lock returned None must never delete the live owner's lock."""
    if handle is None:
        return
    try:
        lock_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- runtime
import logging
import threading

log = logging.getLogger("launcher")


def _bundle_dir() -> Path:
    """Where PyInstaller unpacked our read-only payload (sys._MEIPASS in a
    frozen build; repo root when run from source for debugging)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)              # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _start_streamlit(port: int, app_path: Path) -> None:
    """Run Streamlit's bootstrap in this process (daemon thread). Same server
    `streamlit run app.py` starts, minus the browser auto-open."""
    try:
        from streamlit.web import bootstrap

        # bootstrap.run installs SIGTERM/SIGINT handlers, which raise ValueError
        # outside the main thread; stub them out (verified present in 1.40.2).
        assert hasattr(bootstrap, "_set_up_signal_handler")
        bootstrap._set_up_signal_handler = lambda *a, **k: None
        # The streamlit CLI normally calls load_config_options before run();
        # bare bootstrap.run does not, so apply our options explicitly.
        flag_options = {
            # In a frozen build streamlit can misdetect developmentMode=True
            # (no proper dist install layout), which forbids setting
            # server.port. Force it off.
            "global.developmentMode": False,
            "server.headless": True,
            "server.port": port,
            "server.address": "127.0.0.1",
            "browser.gatherUsageStats": False,
        }
        bootstrap.load_config_options(flag_options=flag_options)
        bootstrap.run(str(app_path), False, [], flag_options)
    except Exception:                              # noqa: BLE001
        log.exception("streamlit server thread crashed")


def _fatal_dialog(message: str) -> None:
    """Native error box — user must never get a silent exit."""
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, "Dhan-Claude Trader", 0x10)


def main() -> int:
    try:
        exe_dir = _exe_dir()
        user_dir = resolve_user_dir(exe_dir=exe_dir, bundle_dir=_bundle_dir())
        logging.basicConfig(filename=str(user_dir / "launcher.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except Exception as e:                         # noqa: BLE001 - no log yet
        _fatal_dialog("Dhan-Claude Trader could not create its data folder.\n\n"
                      f"{e}\n\nTry moving the app out of Program Files.")
        return 1

    lock_path = user_dir / "app.lock"
    lock = acquire_lock(lock_path)
    if lock is None:
        log.info("second instance blocked by %s", lock_path)
        _fatal_dialog("Dhan-Claude Trader is already running.")
        return 1

    try:
        # app.py opens trades.db / reports/ / watchlist.json by relative path —
        # chdir makes all of them resolve inside the persistent user dir.
        os.chdir(user_dir)
        app_path = _bundle_dir() / "app.py"

        port = find_free_port()
        t = threading.Thread(target=_start_streamlit, args=(port, app_path),
                             daemon=True, name="streamlit-server")
        t.start()

        base_url = f"http://127.0.0.1:{port}"
        if not wait_for_health(base_url):
            log.error("streamlit did not become healthy within %ss", HEALTH_TIMEOUT_S)
            _fatal_dialog("Could not start the trading engine.\n\n"
                          f"See log: {user_dir / 'launcher.log'}")
            return 1

        import webview
        webview.create_window("Dhan-Claude Trader", base_url,
                              width=1440, height=900, min_size=(1100, 700))
        webview.start()                        # blocks until window closed
        log.info("window closed; shutting down")
        return 0
    except Exception:                          # noqa: BLE001
        log.exception("launcher crashed")
        _fatal_dialog("Dhan-Claude Trader failed to start.\n\n"
                      f"See log: {user_dir / 'launcher.log'}")
        return 1
    finally:
        release_lock(lock, lock_path)
        # streamlit thread is daemon=True; process exit kills the server.


if __name__ == "__main__":
    sys.exit(main())
