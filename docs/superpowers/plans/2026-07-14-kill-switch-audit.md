# Kill-Switch + Audit Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global kill-switch enforced structurally inside `confirm_and_place`, plus an append-only JSONL audit ledger of every order-lifecycle event.

**Architecture:** Pure `services/audit.py` (best-effort JSONL) and `services/kill_switch.py` (config-backed halt state). `confirm_and_place` checks the halt first and audits every outcome. UI gets a HALT/RESUME toggle + an audit viewer.

**Tech Stack:** Python stdlib (`json`, `datetime`), pytest, Streamlit.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-kill-switch-audit-design.md`](../specs/2026-07-14-kill-switch-audit-design.md)

---

## Before You Start

- Branch `feature/kill-switch-audit` (created). Repo-local git identity configured.
- Read `services/trade_controller.py` (`confirm_and_place`, `prepare_order`, `prepare_btst_order`), `core/config_store.py` (`KEYS`, `get_setting`, `save`), `core/models.OrderResult`.

---

## Task 1: audit ledger

**Files:**
- Create: `services/audit.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_audit.py`:
```python
from services import audit


def test_log_and_read_roundtrip_newest_first(tmp_path):
    p = tmp_path / "audit.jsonl"
    audit.log_event("PLACED", {"symbol": "RELIANCE"}, path=p)
    audit.log_event("HALT", {"reason": "manual"}, path=p)
    events = audit.read_events(path=p, limit=10)
    assert events[0]["event"] == "HALT"          # newest first
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
    # a directory path can't be opened as a file — must be swallowed
    audit.log_event("X", {}, path="")     # no exception
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_audit.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `services/audit.py`**

```python
"""Append-only audit ledger (JSONL). One timestamped line per order-lifecycle event.
Best-effort: never raises, so an audit failure can never block or crash trading."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

AUDIT_PATH = "audit.jsonl"


def log_event(event: str, detail: dict | None = None, *, path=AUDIT_PATH) -> None:
    try:
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "event": event, "detail": detail or {}})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                              # noqa: BLE001 - never block trading
        log.exception("audit log_event failed")


def read_events(path=AUDIT_PATH, limit: int = 100) -> list[dict]:
    try:
        p = Path(path)
        if not p.exists():
            return []
        out = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return list(reversed(out))[:limit]
    except Exception:                              # noqa: BLE001
        log.exception("audit read_events failed")
        return []
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_audit.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/audit.py tests/test_audit.py
git commit -m "feat(audit): append-only JSONL audit ledger (best-effort)"
```

---

## Task 2: kill-switch

**Files:**
- Create: `services/kill_switch.py`
- Modify: `core/config_store.py` (add `KILL_SWITCH` to `KEYS`)
- Test: `tests/test_kill_switch.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_kill_switch.py`:
```python
from core import config_store
from services import audit, kill_switch


def _isolate(monkeypatch, tmp_path):
    settings = tmp_path / "settings.local.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", settings)
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, settings))
    monkeypatch.setattr(config_store.save, "__defaults__", (settings,))
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    # kill_switch.halt/resume call audit.log_event with its default path arg, which was
    # bound at def-time; rebind so events land in tmp too
    monkeypatch.setattr(audit.log_event, "__defaults__", (None,))
    monkeypatch.setattr(audit.log_event, "__kwdefaults__", {"path": str(tmp_path / "audit.jsonl")})


def test_default_not_halted(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert kill_switch.is_halted() is False


def test_halt_then_resume(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    kill_switch.halt("manual test")
    assert kill_switch.is_halted() is True
    kill_switch.resume()
    assert kill_switch.is_halted() is False


def test_halt_writes_audit_event(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    kill_switch.halt("panic")
    events = audit.read_events(path=str(tmp_path / "audit.jsonl"))
    assert any(e["event"] == "HALT" for e in events)


def test_kill_switch_key_registered():
    assert "KILL_SWITCH" in config_store.KEYS
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_kill_switch.py -v`
Expected: FAIL — module + key missing.

- [ ] **Step 3: Add `KILL_SWITCH` to `core/config_store.py` `KEYS`**

Append `"KILL_SWITCH"` to the `KEYS` list (after `"BELL_LEAD_MINUTES"`):
```python
    "BELL_ENABLED", "BELL_LEAD_MINUTES", "KILL_SWITCH",
```

- [ ] **Step 4: Write `services/kill_switch.py`**

```python
"""Global trading kill-switch. Halt state persists in config_store (survives
restart — a crash mid-halt comes back frozen, never accidentally live). The halt is
enforced structurally inside trade_controller.confirm_and_place, not just the UI."""
from __future__ import annotations
from core import config_store
from services import audit


def is_halted() -> bool:
    return str(config_store.get_setting("KILL_SWITCH", "false")).lower() == "true"


def halt(reason: str = "") -> None:
    config_store.save({"KILL_SWITCH": "true"})
    audit.log_event("HALT", {"reason": reason})


def resume() -> None:
    config_store.save({"KILL_SWITCH": "false"})
    audit.log_event("RESUME", {})
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_kill_switch.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add services/kill_switch.py core/config_store.py tests/test_kill_switch.py
git commit -m "feat(kill-switch): config-backed halt state + audit on halt/resume"
```

---

## Task 3: Structural gate in confirm_and_place + PREPARE audit

**Files:**
- Modify: `services/trade_controller.py`
- Test: `tests/test_trade_controller_killswitch.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_trade_controller_killswitch.py`:
```python
from core.models import (BtstCandidate, Instrument, OrderResult, OrderType, Side,
                         TradeMode)
from services.risk_manager import RiskConfig
from services import trade_controller, kill_switch, audit
from data.journal import init_db, list_trades


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="BO1", exec_price=req.price)


def _cand():
    return BtstCandidate(
        instrument=Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                              security_id="1"),
        entry=100.0, target=103.0, stop=98.0, net_score=0.4, close_strength=0.9,
        volume_ratio=1.5, reasons=["x"], gap_risk="gap")


def test_confirm_halted_places_nothing_and_returns_halted(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "is_halted", lambda: True)
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "a.jsonl"))
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.status == "HALTED" and res.ok is False
    assert dhan.placed == []                       # never reached the broker
    assert list_trades(conn) == []                 # never journaled


def test_confirm_not_halted_places(tmp_path, monkeypatch):
    monkeypatch.setattr(kill_switch, "is_halted", lambda: False)
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "a.jsonl"))
    conn = init_db(str(tmp_path / "t.db"))
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=conn)
    assert res.ok and len(dhan.placed) == 1


def test_confirm_halted_writes_audit(tmp_path, monkeypatch):
    apath = str(tmp_path / "a.jsonl")
    monkeypatch.setattr(kill_switch, "is_halted", lambda: True)
    monkeypatch.setattr(audit, "AUDIT_PATH", apath)
    dhan = FakeDhan()
    pending = trade_controller.prepare_btst_order(_cand(), equity=100000,
                                                  cfg=RiskConfig(), day_pnl_value=0,
                                                  open_count=0)
    trade_controller.confirm_and_place(pending, dhan_client=dhan, journal_conn=None)
    events = audit.read_events(path=apath)
    assert any(e["event"] == "HALTED" for e in events)
```

Note: the tests patch `audit.AUDIT_PATH`, but `confirm_and_place` must call
`audit.log_event(event, detail)` WITHOUT an explicit `path=` so it picks up the patched
module-level default at call time. Ensure the implementation calls
`audit.log_event("HALTED", {...})` (no path kwarg) — see step 3. (`log_event`'s `path`
default is evaluated at call from the module global `AUDIT_PATH`? No — Python binds
default args at def time. To make patching `audit.AUDIT_PATH` effective, `log_event`
must read the module global when no path is passed.) **Therefore step 3 also adjusts
`audit.log_event` to default `path=None` and fall back to the current `AUDIT_PATH`
module global inside the function.**

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_trade_controller_killswitch.py -v`
Expected: FAIL — no halt gate yet.

- [ ] **Step 3: Make `audit.log_event` read the module global, then add the gate**

3a. In `services/audit.py`, change `log_event` so patching `AUDIT_PATH` works:
```python
def log_event(event: str, detail: dict | None = None, *, path=None) -> None:
    path = path if path is not None else AUDIT_PATH
    try:
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "event": event, "detail": detail or {}})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                              # noqa: BLE001 - never block trading
        log.exception("audit log_event failed")
```
And `read_events(path=None, limit=100)` similarly resolves `path = path or AUDIT_PATH`
at the top. Re-run `pytest tests/test_audit.py` — still 5 passed (the explicit-path
tests are unaffected; add none). Update `test_kill_switch.py`'s `_isolate` note is moot
now since `AUDIT_PATH` patching suffices — but keep that test file as written (it patches
both, which still works).

3b. In `services/trade_controller.py`, add imports and the gate. Add near the top:
```python
from services import kill_switch, audit
```
Rewrite `confirm_and_place`:
```python
def confirm_and_place(pending: PendingOrder, *, dhan_client, journal_conn,
                      consensus: ConsensusSignal | None = None) -> OrderResult:
    """The ONLY path that places an order. Halted or risk-blocked orders never reach
    the broker. The kill-switch check is the first statement — structurally
    unbypassable, like the no-auto-fire guarantee."""
    req = pending.order_request
    if kill_switch.is_halted():
        audit.log_event("HALTED", {"symbol": req.instrument.symbol})
        return OrderResult(ok=False, mode=dhan_client.mode, status="HALTED",
                           error_message="Trading halted by kill-switch.")
    if not pending.risk_check.allowed:
        audit.log_event("BLOCKED", {"symbol": req.instrument.symbol,
                                    "reasons": pending.risk_check.reasons})
        return OrderResult(ok=False, mode=dhan_client.mode, status="BLOCKED",
                           error_message="; ".join(pending.risk_check.reasons))
    if req.stop_loss is not None and req.target is not None:
        result = dhan_client.place_bracket_order(req)
    else:
        result = dhan_client.place_order(req)
    audit.log_event("PLACED", {"symbol": req.instrument.symbol, "side": req.side.value,
                               "qty": req.qty, "order_id": result.dhan_order_id,
                               "status": result.status})
    if journal_conn is not None:
        from data.journal import log_order
        log_order(journal_conn, req, result, consensus=consensus)
    return result
```
3c. Add a `PREPARE` audit line at the end of both `prepare_order` and
`prepare_btst_order`, just before their `return PendingOrder(...)`:
```python
    audit.log_event("PREPARE", {"symbol": <instrument>.symbol,
                                "allowed": check.allowed})
```
(For `prepare_order` the instrument is `instrument`; for `prepare_btst_order` it's
`candidate.instrument`. Use the local `check` variable each already computes.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_trade_controller_killswitch.py tests/test_trade_controller.py tests/test_trade_controller_btst.py tests/test_audit.py -v`
Expected: all pass (new gate tests + existing confirm/BTST tests still green — they run
with `is_halted()` defaulting False via real config, which has no `KILL_SWITCH`).

- [ ] **Step 5: Commit**

```bash
git add services/trade_controller.py services/audit.py tests/test_trade_controller_killswitch.py
git commit -m "feat(kill-switch): structural halt gate in confirm_and_place + audit events"
```

---

## Task 4: UI — HALT toggle + audit viewer (manual verify)

**Files:**
- Modify: `app.py`, `pages/1_Reports.py`

- [ ] **Step 1: Dashboard HALT/RESUME (`app.py`)** — near the top header block (after the
  mode/refresh row, before the risk panel), add:
```python
from services import kill_switch as _ks
if _ks.is_halted():
    st.error("🔴 TRADING HALTED by kill-switch — no orders will be placed.")
    if st.button("▶ Resume trading"):
        _ks.resume()
        st.rerun()
else:
    if st.button("🔴 HALT trading"):
        _ks.halt("manual halt from dashboard")
        st.rerun()
```
Also disable the confirm dialog's place button when halted (defense in depth): in the
confirm dialog, add `or _ks.is_halted()` to the place button's `disabled=` condition, and
show a caption "Halted — resume to place." when halted.

- [ ] **Step 2: Reports audit viewer (`pages/1_Reports.py`)** — add
  `from services import audit` and, near the bottom, an expander:
```python
with st.expander("🧾 Audit ledger (recent)", expanded=False):
    _events = audit.read_events(limit=100)
    if _events:
        st.dataframe(pd.DataFrame(_events), use_container_width=True)
    else:
        st.caption("No audit events yet.")
```

- [ ] **Step 3: Manual verification**

Run `streamlit run app.py`:
- Dashboard shows a red HALT button. Click it → halted banner appears, HALT becomes
  RESUME, and attempting to confirm a signal is refused (button disabled + a HALTED
  result if forced).
- Reports "Audit ledger" expander lists events (HALT, PREPARE, etc.), newest first.
- Click Resume → banner clears, placement allowed again.
- Confirm the halt persists: halt, fully close the app, reopen → still halted (banner
  shows) until you resume.

- [ ] **Step 4: Commit**

```bash
git add app.py pages/1_Reports.py
git commit -m "feat(kill-switch): dashboard HALT/RESUME toggle + Reports audit viewer"
```

---

## Task 5: Full-suite gate

- [ ] **Step 1:** `pytest tests/ -q` — all green (new audit/kill-switch/gate tests + every
  prior test; confirm the existing `confirm_and_place` tests still pass with the gate).
- [ ] **Step 2:** `streamlit run app.py` boots; HALT toggle + audit viewer render; no
  traceback. **Important:** after manual testing, ensure the app is left NOT halted
  (resume) and remove any stray `audit.jsonl`/`KILL_SWITCH` from the dev settings so the
  repo/dev state is clean. Fix + re-run if anything fails.

---

## Self-Review Notes

- **Spec coverage:** §2 modules → T1 (audit), T2 (kill_switch + config key), T3 (gate).
  §3 kill_switch → T2. §4 audit → T1 (+ T3 makes `AUDIT_PATH` patchable). §5 structural
  gate → T3 with the key "halted places nothing + not journaled" test. §6 UI → T4. §7
  edges → best-effort audit (T1 bad-path test), persist-across-restart (config-backed,
  T4 manual step), is_halted default false (existing tests stay green). §8 testing → T1–T3
  unit; T4 manual.
- **Design refinement caught:** `audit.log_event`/`read_events` must resolve `AUDIT_PATH`
  from the module global at call time (not a def-time default) so tests and the running
  app can point the ledger at the right file; T3 step 3a makes this change and the note
  flags why.
- **No placeholders**; full code shown. **Type consistency:** `is_halted()/halt(reason)/
  resume()`, `log_event(event, detail, *, path=None)/read_events(path=None, limit)` match
  across modules, tests, and call sites; `OrderResult(status="HALTED")` consistent.
- **No-auto-fire preserved and strengthened:** the halt check is the first statement of
  the sole placing function; risk gate + two-step confirm unchanged.
