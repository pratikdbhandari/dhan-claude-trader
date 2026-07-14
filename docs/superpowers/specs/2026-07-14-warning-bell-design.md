# Market-Open Warning Bell Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/market_clock.minutes_to_open` (already built + tested), `desktop/launcher.py` (persistent process), `core/config_store`, `pages/4_Settings.py`.
**Part of the 4-feature sequence** (BTST ✓, behavior diagnostics ✓, **warning bell**, UI reface). 

---

## 1. Purpose

Ring an audible + visible alarm a configurable number of minutes (default 10) before
the NSE cash open (09:15 IST) — a heads-up to be at the desk for the session. Fires
once per trading day.

**Key constraint (drives the whole design):** Streamlit is request-driven — no page
open means no code runs, so it cannot fire a timed alarm. The bell therefore lives in
the **desktop launcher's background thread** (`desktop/launcher.py`), which is a
persistent process for as long as the app window is open. This means the bell fires
only while DhanTrader is running. An always-on alarm that works with the app closed
(Windows Task Scheduler) is a **documented follow-up, not built here**.

**Principles:** pure decision logic unit-tested; the launcher thread only performs the
side effects (sound, popup); failures never crash the app.

**Out of scope:** Task Scheduler / OS-level alarm, snooze, custom sound files,
multiple alarms, holiday calendar (inherits market_clock's weekend-only behavior).

---

## 2. Modules

```
services/bell.py     NEW, pure: should_ring(now, *, enabled, lead_minutes,
                       last_rung_date) -> bool. Uses market_clock.minutes_to_open.
desktop/launcher.py  ADD a daemon bell thread + the ring side effect (winsound +
                       native popup). Started from main() alongside the streamlit
                       thread; stopped on process exit.
core/config_store.py ADD "BELL_ENABLED", "BELL_LEAD_MINUTES" to KEYS.
pages/4_Settings.py  ADD an on/off toggle + lead-minutes input, saved to config_store.
```

---

## 3. Decision Logic (`services/bell.py`)

```python
def should_ring(now, *, enabled: bool, lead_minutes: int,
                last_rung_date) -> bool:
    """True when the pre-open bell should fire now.
    now: tz-aware datetime. last_rung_date: date | None of the last ring."""
```

Rings when ALL hold:
1. `enabled` is True.
2. `market_clock.minutes_to_open(now)` is not None (market not already open) — call it `m`.
3. `1 <= m <= lead_minutes` (inside the pre-open lead window; `>=1` so it doesn't
   fire the instant the market opens).
4. `last_rung_date != now (IST) .date()` (haven't already rung today).

Pure and injectable (`now` passed in; `market_clock` handles IST + weekends —
weekends roll `minutes_to_open` to Monday, so `m` is huge and condition 3 fails until
Monday ~09:05). The caller owns `last_rung_date` state and updates it after ringing.

---

## 4. Launcher Bell Thread (`desktop/launcher.py`)

- A new daemon thread started in `main()` next to the streamlit thread, running a loop:
  every ~30s, read `enabled` (`BELL_ENABLED`, default true) and `lead_minutes`
  (`BELL_LEAD_MINUTES`, default 10) fresh from `config_store` (so Settings edits take
  effect without a restart), call `bell.should_ring(datetime.now(tz), ...)`, and if
  True: `_ring(m)` then set the in-thread `last_rung_date = today`.
- `_ring(minutes)`: `winsound.MessageBeep`/`PlaySound` (stdlib, no new dep) inside a
  try/except (swallow sound errors), then a native popup "Market opens in {minutes}
  minutes." via the existing `ctypes` MessageBox helper. Sound failure must not
  suppress the popup.
- The loop is wrapped so any exception is logged and the loop continues — the bell can
  never crash the app or the trading UI. Thread is `daemon=True`; process exit ends it.
- Config read each tick is best-effort; a config read error falls back to defaults
  (enabled, 10 min) and is logged.

The bell thread is **only** added to the packaged/launcher path. Running the app via
`streamlit run app.py` (dev/browser) has no launcher and therefore no bell — expected,
matching the constraint in §1.

---

## 5. Settings UI (`pages/4_Settings.py`)

Add a "Market-open bell" section: a checkbox bound to `BELL_ENABLED` and a number input
(min 1, max 60, default 10) bound to `BELL_LEAD_MINUTES`, saved through the page's
existing `config_store.save` flow. A caption notes the bell fires only while the app is
open.

---

## 6. Error / Edge Handling

- Market already open → `minutes_to_open` None → no ring.
- Weekend → market_clock rolls to Monday → no ring until Monday's lead window.
- Once-per-day dedup via `last_rung_date`.
- `winsound` failure (no audio device) → caught; popup still shows.
- Bell-thread exception → logged, loop continues, app unaffected.
- Invalid/missing config values → fall back to enabled + 10 min.

---

## 7. Testing (TDD, existing pytest style)

- `bell.should_ring`: rings inside the window (e.g. m=5, lead=10); no ring when m=0/None
  (open); no ring when disabled; no ring when already rung today; no ring when m >
  lead_minutes; boundary m == lead_minutes rings; m == 1 rings; different day after a
  prior ring rings again. `market_clock` injected via real function with fixed `now`.
- Launcher bell thread + winsound + MessageBox = manual verification (side-effecting,
  like `main()` itself): temporarily set lead_minutes high / clock near open, confirm
  one sound + popup, confirm it does not re-fire the same day.
