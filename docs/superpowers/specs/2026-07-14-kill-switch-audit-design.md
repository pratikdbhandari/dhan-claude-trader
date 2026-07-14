# Kill-Switch + Audit Ledger Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/trade_controller.confirm_and_place` (the sole order-placing function), `core/config_store`, `data/journal` (for the data dir location), `app.py`, `pages/1_Reports.py`.
**Origin:** Vibe-Trading review pick — safety hardening (kill-switch + immutable audit ledger).

---

## 1. Purpose

Add a global **kill-switch** that instantly freezes all order placement, enforced
structurally inside `confirm_and_place` so no caller can bypass it, and an append-only
**audit ledger** recording every order-lifecycle event.

**Principles:** the halt gate is structural (same style as the no-auto-fire guarantee —
it lives in `confirm_and_place`, not just the UI); audit writes are best-effort and
never block or crash the trading path; halt state persists across restarts.

**Out of scope:** per-user permissions, remote/kill-by-API, auto-halt on loss triggers
(the risk_manager daily-loss gate already exists separately), log rotation/retention.

---

## 2. Modules

```
services/kill_switch.py   NEW: is_halted() -> bool, halt(reason) -> None,
                            resume() -> None. State in config_store["KILL_SWITCH"]
                            ("true"/"false"), so it survives restarts. halt/resume
                            also write an audit event.
services/audit.py         NEW: log_event(event, detail, *, path=AUDIT_PATH) appends one
                            JSONL line {ts, event, detail}; read_events(path, limit)
                            returns the most recent events (newest first). Best-effort:
                            any write/read error is swallowed (returns []/no-op).
services/trade_controller.py  CHANGE confirm_and_place: FIRST check kill_switch.is_halted()
                            -> if halted, audit "HALTED" and return
                            OrderResult(ok=False, status="HALTED", ...) without touching
                            the broker or journal. Else audit "PLACED"/"BLOCKED".
                            prepare_order + prepare_btst_order audit "PREPARE".
core/config_store.py      ADD "KILL_SWITCH" to KEYS.
app.py                    Dashboard: prominent HALT/RESUME toggle + halted banner;
                            confirm path also disabled when halted (defense in depth).
pages/1_Reports.py        Audit-ledger viewer (recent events).
```

`AUDIT_PATH = "audit.jsonl"` (relative — resolves next to `trades.db` in the working
dir, i.e. the desktop app's data folder / repo root in dev, same convention as the
journal).

---

## 3. kill_switch (`services/kill_switch.py`)

```python
def is_halted() -> bool:
    return str(config_store.get_setting("KILL_SWITCH", "false")).lower() == "true"

def halt(reason: str = "") -> None:
    config_store.save({"KILL_SWITCH": "true"})
    audit.log_event("HALT", {"reason": reason})

def resume() -> None:
    config_store.save({"KILL_SWITCH": "false"})
    audit.log_event("RESUME", {})
```
Config-backed so a crash mid-halt stays halted on restart (fail-safe: the app comes
back frozen, not accidentally live).

## 4. audit (`services/audit.py`)

```python
AUDIT_PATH = "audit.jsonl"

def log_event(event: str, detail: dict | None = None, *, path=AUDIT_PATH) -> None:
    """Append one JSONL line {ts, event, detail}. Best-effort — never raises."""

def read_events(path=AUDIT_PATH, limit: int = 100) -> list[dict]:
    """Return up to `limit` most-recent events, newest first. [] on any error."""
```
`log_event` opens the file in append mode, writes
`json.dumps({"ts": <utc iso>, "event": event, "detail": detail or {}})` + newline,
wrapped in try/except that logs and swallows. `read_events` reads all lines, parses each
tolerantly (skip bad lines), returns the last `limit` reversed.

## 5. confirm_and_place gate (`services/trade_controller.py`)

```python
def confirm_and_place(pending, *, dhan_client, journal_conn, consensus=None):
    if kill_switch.is_halted():
        audit.log_event("HALTED", {"symbol": pending.order_request.instrument.symbol})
        return OrderResult(ok=False, mode=dhan_client.mode, status="HALTED",
                           error_message="Trading halted by kill-switch.")
    if not pending.risk_check.allowed:
        audit.log_event("BLOCKED", {"symbol": ..., "reasons": pending.risk_check.reasons})
        return OrderResult(..., status="BLOCKED", ...)     # existing behavior
    result = ... place ...                                 # existing place path
    audit.log_event("PLACED", {"symbol": ..., "side": ..., "qty": ...,
                               "order_id": result.dhan_order_id, "status": result.status})
    ... journal.log_order ...
    return result
```
The halt check is the very first statement — structurally unbypassable, mirroring the
no-auto-fire guarantee. `prepare_order`/`prepare_btst_order` add a `PREPARE` audit line.
UI exit handlers add an `EXIT` line at their call sites.

## 6. UI

- **Dashboard** (`app.py`): a prominent red **HALT TRADING** button when live, or a
  **RESUME** button when halted, at the top; a persistent halted banner when
  `kill_switch.is_halted()`. The confirm dialog's place button is also disabled when
  halted (defense in depth — the structural gate is the real guarantee).
- **Reports** (`pages/1_Reports.py`): an "Audit ledger" expander showing
  `audit.read_events(limit=100)` as a table (ts, event, detail).

## 7. Error / edge handling

- Audit write/read failure → swallowed (logged), never blocks trading or crashes a page.
- Halt persists across restart (config-backed) — fail-safe frozen, never accidentally live.
- `is_halted()` defaults false (no `KILL_SWITCH` key) → existing callers/tests unaffected.
- Halted `confirm_and_place` never contacts the broker and never journals — pure refusal.
- JSONL append is per-line; a partially written final line is skipped by tolerant parse.

## 8. Testing

- `kill_switch`: `halt()` → `is_halted()` True; `resume()` → False; state via an isolated
  config path (monkeypatched) so tests don't touch real settings; halt/resume emit audit
  events (audit path monkeypatched to tmp).
- `audit`: `log_event` then `read_events` round-trips (newest first, respects limit);
  write to an unwritable path is swallowed (no raise); malformed line skipped on read.
- `trade_controller.confirm_and_place`: **halted → returns HALTED, places nothing, does
  not journal** (the key safety test, with `kill_switch.is_halted` monkeypatched True);
  not halted → places as before; risk-blocked → BLOCKED as before; each path writes the
  expected audit event (audit path monkeypatched).
- Pages verified by running.
