# Market-Open Warning Bell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ring an audible + visible alarm a configurable number of minutes (default 10) before the 09:15 IST market open, once per trading day, from the desktop launcher's background thread.

**Architecture:** Pure `services/bell.py` decides when to ring (via already-tested `market_clock.minutes_to_open`); a daemon thread in `desktop/launcher.py` polls it and performs the side effects (winsound + native popup); `pages/4_Settings.py` + `config_store` provide the on/off toggle and lead-minutes.

**Tech Stack:** Python 3.13 stdlib (`winsound`, `ctypes`, `threading`, `datetime`), Streamlit, pytest.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-warning-bell-design.md`](../specs/2026-07-14-warning-bell-design.md)

---

## Before You Start

- Branch `feature/warning-bell` (already created). Repo-local git identity configured (plain `git commit`).
- Read `services/market_clock.py` (`minutes_to_open`, `IST`), `core/config_store.py` (`KEYS`, `get_setting`, `save`), `desktop/launcher.py` (`main()`, `_fatal_dialog`, the streamlit-thread pattern), `pages/4_Settings.py` (its save flow).

---

## Task 1: bell.should_ring

**Files:**
- Create: `services/bell.py`
- Test: `tests/test_bell.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_bell.py`:
```python
from datetime import date, datetime, timezone, timedelta

from services.bell import should_ring

IST = timezone(timedelta(hours=5, minutes=30))


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# 2026-07-14 is a Tuesday. Open 09:15. 09:05 -> 10 min to open.
def test_rings_inside_lead_window():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_rings_at_exact_lead_boundary():
    # 09:05 is exactly 10 min before open
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_rings_one_minute_before_open():
    assert should_ring(_ist(2026, 7, 14, 9, 14), enabled=True, lead_minutes=10,
                       last_rung_date=None) is True


def test_no_ring_before_lead_window():
    # 08:50 -> 25 min to open, lead 10
    assert should_ring(_ist(2026, 7, 14, 8, 50), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_market_open():
    # 10:00 -> minutes_to_open None
    assert should_ring(_ist(2026, 7, 14, 10, 0), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_disabled():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=False, lead_minutes=10,
                       last_rung_date=None) is False


def test_no_ring_when_already_rung_today():
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=date(2026, 7, 14)) is False


def test_rings_again_on_a_new_day():
    # last rung yesterday -> today rings
    assert should_ring(_ist(2026, 7, 14, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=date(2026, 7, 13)) is True


def test_no_ring_on_weekend():
    # 2026-07-18 Saturday 09:05 -> minutes_to_open rolls to Monday, huge -> no ring
    assert should_ring(_ist(2026, 7, 18, 9, 5), enabled=True, lead_minutes=10,
                       last_rung_date=None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bell.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.bell'`

- [ ] **Step 3: Write `services/bell.py`**

```python
"""Market-open warning bell — pure decision logic. Whether to ring the pre-open
alarm right now. The launcher's background thread owns the side effects (sound,
popup) and the last_rung_date state; this module only decides."""
from __future__ import annotations
from datetime import date, datetime

from services import market_clock


def should_ring(now: datetime, *, enabled: bool, lead_minutes: int,
                last_rung_date: date | None) -> bool:
    """True when the pre-open bell should fire at `now`.

    Rings when enabled, the market is not already open, we are within the
    [1, lead_minutes] pre-open window, and we have not already rung today."""
    if not enabled:
        return False
    m = market_clock.minutes_to_open(now)
    if m is None:                       # market already open
        return False
    if not (1 <= m <= lead_minutes):
        return False
    today = now.astimezone(market_clock.IST).date()
    return last_rung_date != today
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bell.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add services/bell.py tests/test_bell.py
git commit -m "feat(bell): pure pre-open ring decision over market_clock"
```

---

## Task 2: Config keys + Settings UI

**Files:**
- Modify: `core/config_store.py`
- Modify: `pages/4_Settings.py`
- Test: `tests/test_config_store_bell.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config_store_bell.py`:
```python
from core import config_store


def test_bell_keys_registered():
    assert "BELL_ENABLED" in config_store.KEYS
    assert "BELL_LEAD_MINUTES" in config_store.KEYS


def test_bell_settings_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    config_store.save({"BELL_ENABLED": "true", "BELL_LEAD_MINUTES": "15"}, path=p)
    assert config_store.get_setting("BELL_ENABLED", path=p) == "true"
    assert config_store.get_setting("BELL_LEAD_MINUTES", path=p) == "15"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_store_bell.py -v`
Expected: FAIL — keys not in `KEYS`.

- [ ] **Step 3: Edit `core/config_store.py`**

Add the two keys to the `KEYS` list (append after `"ACCOUNT_CAPITAL"`):
```python
KEYS = [
    "DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN",
    "ANTHROPIC_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY",
    "SIGNAL_SOURCE", "TRADE_MODE",
    "MAX_DAILY_LOSS", "MAX_RISK_PER_TRADE_PCT", "MAX_OPEN_POSITIONS", "ACCOUNT_CAPITAL",
    "BELL_ENABLED", "BELL_LEAD_MINUTES",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_store_bell.py -v`
Expected: 2 passed

- [ ] **Step 5: Add the Settings UI**

In `pages/4_Settings.py`, add a section (follow the file's existing widget + save
pattern; the exact save call must match how other settings on that page persist — read
the file and mirror it). The section renders:
```python
st.markdown("#### Market-open bell")
st.caption("Rings a chime + popup before the 09:15 open. Fires only while the app is open.")
_bell_on = st.checkbox(
    "Enable pre-open bell",
    value=str(config_store.get_setting("BELL_ENABLED", "true")).lower() == "true")
_bell_lead = st.number_input(
    "Minutes before open", min_value=1, max_value=60,
    value=int(config_store.get_setting("BELL_LEAD_MINUTES", "10")))
if st.button("Save bell settings"):
    config_store.save({"BELL_ENABLED": "true" if _bell_on else "false",
                       "BELL_LEAD_MINUTES": str(int(_bell_lead))})
    st.success("Bell settings saved.")
```
Ensure `from core import config_store` is present (it almost certainly already is —
check imports; add only if missing).

- [ ] **Step 6: Manual check**

Run `streamlit run app.py`, open Settings, toggle the bell + change minutes, Save,
reload the page — values persist (reads back from `config_store`).

- [ ] **Step 7: Commit**

```bash
git add core/config_store.py pages/4_Settings.py tests/test_config_store_bell.py
git commit -m "feat(bell): config keys + Settings toggle and lead-minutes"
```

---

## Task 3: Launcher bell thread (manual verify)

**Files:**
- Modify: `desktop/launcher.py`

Side-effecting (thread + sound + popup); verified by running, not unit-tested. The
decision logic is fully covered in Task 1.

- [ ] **Step 1: Add the ring + bell-loop functions**

In `desktop/launcher.py`, after `_fatal_dialog` (around line 152), add:

```python
def _ring(minutes: int) -> None:
    """Audible chime + native popup. Sound failure must not suppress the popup."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:                              # noqa: BLE001 - no audio device etc.
        log.exception("bell sound failed")
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None, f"Market opens in {minutes} minutes.", "Dhan-Claude Trader", 0x40)


def _bell_loop(stop: "threading.Event") -> None:
    """Poll every 30s; ring once per day inside the configured pre-open window.
    Reads config each tick so Settings changes take effect without a restart."""
    from datetime import datetime, timezone
    from services import bell, market_clock
    from core import config_store
    last_rung = None
    while not stop.is_set():
        try:
            enabled = str(config_store.get_setting("BELL_ENABLED", "true")).lower() == "true"
            try:
                lead = int(config_store.get_setting("BELL_LEAD_MINUTES", "10"))
            except (TypeError, ValueError):
                lead = 10
            now = datetime.now(timezone.utc)
            if bell.should_ring(now, enabled=enabled, lead_minutes=lead,
                                last_rung_date=last_rung):
                m = market_clock.minutes_to_open(now)
                _ring(m if m is not None else lead)
                last_rung = now.astimezone(market_clock.IST).date()
        except Exception:                          # noqa: BLE001 - never kill the app
            log.exception("bell loop tick failed")
        stop.wait(30)
```

- [ ] **Step 2: Start/stop the bell thread in `main()`**

In `main()`, right after the streamlit thread is started (`t.start()`), add:
```python
        bell_stop = threading.Event()
        bell_thread = threading.Thread(target=_bell_loop, args=(bell_stop,),
                                       daemon=True, name="bell")
        bell_thread.start()
```
And in the `finally:` block, before/after `release_lock(...)`, signal it to stop:
```python
    finally:
        bell_stop.set() if 'bell_stop' in dir() else None
        release_lock(lock, lock_path)
```
Note: `bell_stop` is defined inside the `try`; guard the `finally` reference as shown
(or initialise `bell_stop = None` just before the `try` and `if bell_stop: bell_stop.set()`).
Prefer initialising `bell_stop = None` before the `try` for clarity:
```python
    bell_stop = None
    try:
        ...
        bell_stop = threading.Event()
        bell_thread = threading.Thread(target=_bell_loop, args=(bell_stop,),
                                       daemon=True, name="bell")
        bell_thread.start()
        ...
    finally:
        if bell_stop is not None:
            bell_stop.set()
        release_lock(lock, lock_path)
```
Use this `bell_stop = None` form — do not use the `dir()` hack.

- [ ] **Step 3: Verify import + tests still pass**

Run: `python -c "import desktop.launcher"` (silent) and `pytest tests/test_bell.py -q` (9 passed).

- [ ] **Step 4: Manual verification (source run)**

To exercise the ring without waiting for 09:05: temporarily set `BELL_LEAD_MINUTES` very
high (e.g. via Settings, or a scratch value) so "minutes to open" falls inside the
window during a weekday session-adjacent time, run `python -m desktop.launcher`, and
confirm exactly one chime + popup, and that it does not re-fire on the next 30s tick
(same-day dedup). Then restore the setting. Note in the commit that this is manual.

- [ ] **Step 5: Commit**

```bash
git add desktop/launcher.py
git commit -m "feat(bell): launcher daemon thread rings pre-open alarm (sound + popup)"
```

---

## Task 4: Full-suite gate

**Files:** none.

- [ ] **Step 1: Run the entire suite**

Run: `pytest tests/ -q`
Expected: all green — new bell/config tests plus every pre-existing test.

- [ ] **Step 2: Confirm the app boots**

Run: `streamlit run app.py` — Settings page shows the bell section, no traceback. Close. Fix and re-run if anything fails.

---

## Self-Review Notes

- **Spec coverage:** §2 modules → T1 (bell.py), T2 (config + Settings), T3 (launcher thread). §3 decision logic (enabled / not-open / 1..lead / once-per-day) → T1 with 9 tests incl. boundary + weekend + new-day. §4 launcher thread (30s poll, config each tick, `_ring` sound-then-popup with sound-failure guard, exception-safe loop, daemon + stop event) → T3. §5 Settings UI → T2. §6 edges → T1 tests + T3 guards. §7 testing → T1 TDD; launcher manual.
- **No placeholders**; all code shown. The one judgement call (Settings save flow) instructs mirroring the file's existing pattern and shows the widget code.
- **Type consistency:** `should_ring(now, *, enabled, lead_minutes, last_rung_date)` identical across spec, impl, tests, and the launcher call; `_ring(minutes)` and `_bell_loop(stop)` match their call sites; config keys `BELL_ENABLED`/`BELL_LEAD_MINUTES` consistent everywhere.
- **Constraint honored:** bell only in launcher path; dev `streamlit run` has none (documented). Task Scheduler deferred.
