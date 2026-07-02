# Desktop .exe Packaging Design

**Date:** 2026-07-02
**Status:** Approved
**Depends on:** the existing Streamlit app (`app.py`, `pages/*`, `services/*`, `core/*`, `data/*`, `ui/*`) — none of it is modified.
**Relation to other work:** independent of the mobile API layer spec/plan (2026-07-01), which stays parked. Nothing here blocks or changes that work.

---

## 1. Purpose

Package the existing Dhan-Claude Trader as a double-click Windows application:
`DhanTrader.exe` opens a native window with the full dashboard — no browser tab, no
visible console, no `run_app.bat`, no Python installation required on the target
machine.

**Non-goals:** no rewrite of any trading logic or UI; no code signing / auto-update /
Microsoft Store distribution; no multi-user installer; macOS/Linux packaging.

**Approach chosen:** PyInstaller bundle + pywebview native window (Edge WebView2,
preinstalled on Windows 11). Rejected alternatives: Electron shell (adds a Node
toolchain and ~150 MB for the same result) and a PyQt6 rewrite (months of effort,
throws away the tested Streamlit UI).

---

## 2. Architecture

```
DhanTrader.exe  (PyInstaller onedir bundle)
   └─ desktop/launcher.py  (new, the only new runtime code)
        1. resolve user-data dir (next to the .exe)
        2. pick a free localhost port
        3. start Streamlit programmatically (headless, same app.py as today)
        4. poll http://127.0.0.1:<port>/_stcore/health until ready (timeout 60s)
        5. open pywebview native window on that URL
        6. window closed -> terminate the Streamlit server, exit
```

The Streamlit server is an implementation detail the user never sees. Everything
stays on localhost; nothing is exposed to the network (`--server.address=127.0.0.1`).

---

## 3. New Files

```
desktop/
  __init__.py
  launcher.py        find_free_port(), wait_for_health(), resolve_user_dir(),
                     start_streamlit(), main() — pure functions testable without
                     actually launching Streamlit or a window
  build.spec         PyInstaller spec: entry=launcher, collects streamlit metadata
                     + hidden imports, bundles app.py/pages/ui/services/core/data
                     source tree and the default *.json config files
  build_exe.bat      one-command build: pip install -r requirements-desktop.txt,
                     pyinstaller desktop/build.spec, output in dist/DhanTrader/
requirements-desktop.txt   pywebview + pyinstaller pins (build-time extras; the
                     main requirements.txt is unchanged)
tests/desktop/
  test_launcher.py   unit tests for the launcher's pure functions
```

---

## 4. User Data vs. Bundled Code

Bundled inside the .exe (read-only, replaced on every rebuild): all Python code,
`strategies.json`, `providers.json`, `charges.json`, `watchlist.json` defaults.

External, next to the .exe in a `data/` folder created on first run (survives
app updates): `trades.db` (journal), `reports/`, instrument-master cache. Secrets
continue to live in `~/.dhan_claude_trader/settings.local.json` via the existing
`core/config_store.py` — the Settings page keeps working identically, and `.env`
remains a developer-only mechanism.

The launcher sets the process working directory to the external `data/` dir's
parent so all existing relative paths (`trades.db`, `reports/`, `watchlist.json`)
resolve there. On first run it copies the bundled default `*.json` config files
into that dir if absent, so the user can edit their watchlist without rebuilding.

---

## 5. Error Handling

- Streamlit fails to start or health check times out → native error dialog
  ("could not start — see log") + log file `data/launcher.log`; never a silent exit.
- Port race (free port taken between probe and bind) → retry with a new port, 3x.
- WebView2 runtime missing (old Windows 10) → detected by pywebview; error dialog
  with the Microsoft download link.
- Second instance launched while one is running → new instance detects the lock
  file, focuses nothing (webview can't), shows "already running" dialog, exits.

---

## 6. Testing

- `tests/desktop/test_launcher.py`, same pytest style as the rest of the repo:
  free-port selection, health-poll success/timeout (fake HTTP fn injected),
  user-dir resolution + first-run config copy (tmp_path), lock-file behavior.
- The PyInstaller build itself is verified manually via a checklist (build, launch
  exe, dashboard renders, place a PAPER order, journal row written next to exe,
  close window, process tree exits). Build artifacts (`build/`, `dist/`) are
  gitignored.

---

## 7. Known Risks

- **Streamlit under PyInstaller** is the main risk: it loads modules dynamically
  and reads its own package metadata. Mitigation: `collect_all("streamlit")` in
  the spec plus explicit hidden imports; the plan verifies the frozen build boots
  before any polish tasks.
- **Bundle size** ~300–500 MB (pandas/numpy/plotly/streamlit). Accepted; this is
  a personal tool, not a download-optimized product.
