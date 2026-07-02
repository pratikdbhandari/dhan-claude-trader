# Mobile API Layer Design

**Date:** 2026-07-01
**Status:** Approved
**Depends on:** Phase B3 (`risk_manager`, `trade_controller`), Phase B4 (`instruments`, `eod_report`), `services/screener.py`, `services/options_chain.py`, `services/options_payoff.py`, `core/readiness.py`, `core/config_store.py`
**Followed by:** a separate Android app spec (native Kotlin/Compose client), brainstormed once this API's contract is stable.

---

## 1. Purpose

Add a REST API in front of the existing trading engine so a native Android app can
review signals, confirm trades, and check positions/reports from anywhere — without
touching any existing trading logic. The desktop Streamlit app (`app.py`) is unaffected
and keeps running as-is; the API is a second, independent presentation layer over the
same service modules.

**Principles carried over from the desktop app (non-negotiable):**
- No order can fire without two separate, authenticated HTTP calls (prepare, then
  confirm) — the same state machine `trade_controller` already enforces for the
  Streamlit confirm dialog.
- All business logic stays in the existing `services/`/`core/`/`data/` modules. The API
  layer only translates HTTP ↔ those modules, exactly like `app.py` only renders.
- Dhan credentials and `.env` never leave the local machine. The API runs on the same
  PC as today; only the HTTP endpoint is exposed externally.

**Explicitly out of scope for this spec:** the Android app itself, Play Store
distribution, multi-user support, Options/Screener UI redesign (endpoints just expose
existing computed data), any change to risk limits or the confirm state machine's
semantics.

---

## 2. Architecture

```
                     Android app (separate spec)
                              │  HTTPS (JWT bearer)
                              ▼
                    Cloudflare Tunnel (stable public URL)
                              │
                              ▼
                  ┌─────────────────────────┐
                  │   api/  (FastAPI, new)   │
                  │  - auth (Supabase JWKS)  │
                  │  - routers/*             │
                  │  - scheduler (asyncio)   │
                  │  - push (FCM)            │
                  └───────────┬─────────────┘
                              │ direct in-process calls
                              ▼
      services/*, core/*, data/*   (unchanged — same code app.py already calls)
                              │
                              ▼
                    Dhan API · SQLite journal
```

Supabase provides **Auth only** (login → JWT) plus one small table, `push_tokens`
(device FCM token per login). It does not store trading data — the SQLite journal
remains the single source of truth for positions, orders, and P&L, exactly as today.
Firebase Cloud Messaging delivers push alerts for new signals.

The API and Streamlit both run on the same machine and both call the same `services/`
modules directly (in-process function calls, not HTTP) — there is no duplication of
trading logic between the two presentation layers.

---

## 3. New Modules (`api/`)

```
api/
  __init__.py
  main.py            FastAPI app: CORS, startup (load_config), router registration
  deps.py            get_config(), get_dhan_client(), get_journal_conn() — mirrors
                     what app.py wires up today, as FastAPI dependencies
  auth.py            verify_jwt(token) -> user_id, using Supabase project's JWKS
                     (fetched once at startup, cached); raises 401 on invalid/expired
  state.py           PendingStore: in-memory dict {pending_id: (PendingOrder, ts)}
                     with TTL = SIGNAL_COOLDOWN_SECONDS; used by routers/signals.py
  scheduler.py       asyncio background task: every SIGNAL_COOLDOWN_SECONDS, runs
                     signal_engine.generate() per watchlist instrument (same call
                     app.py's auto-refresh makes), stores non-HOLD results in
                     PendingStore, pushes FCM for signals not already pushed
  push.py            send_push(token, title, body, data) via FCM HTTP v1 API
  supabase_client.py thin wrapper: read/write push_tokens table over Supabase REST
  schemas.py         Pydantic models for requests/responses (SignalOut, PositionOut,
                     ConfirmResponse, RiskPanelOut, ReadinessOut, etc.) — shaped from
                     core/models.py dataclasses, not replacing them
  routers/
    signals.py       GET /signals/pending
                     POST /signals/{pending_id}/confirm
    positions.py     GET /positions
                     POST /positions/{security_id}/exit
    reports.py       GET /reports/pnl
                     GET /reports/eod?date=YYYY-MM-DD
    screener.py      GET /screener?preset=...
    options.py       GET /options/chain?symbol=...
                     GET /options/payoff?symbol=...&legs=...
    settings.py      GET /settings/risk
                     PUT /settings/risk
                     GET /settings/readiness
    push.py          POST /push/register  {token: str}
```

No changes to any file outside `api/`.

---

## 4. Signal Lifecycle (the safety-critical path)

Today, `app.py` holds one `pending: PendingOrder` in `st.session_state` between the
user's "Select" click and the confirm dialog's "Place Order" click — both in the same
browser session. The API has no equivalent session, so pending state moves server-side:

1. **Scheduler tick** (every `SIGNAL_COOLDOWN_SECONDS`, default 300s): for each
   watchlist instrument, calls `signal_engine.generate(...)` — the identical call
   `app.py` makes on auto-refresh. Non-HOLD consensus results are wrapped via
   `trade_controller.prepare_order(...)` (this already runs `pre_trade_check` — no
   behavior change) and stored in `PendingStore` keyed by a generated `pending_id`.
   Signals already pushed are not re-pushed on the next tick (dedup by instrument +
   signal fingerprint).
2. **Push**: for each newly-stored pending signal, `push.send_push(...)` fires an FCM
   notification to every registered token: *"New signal: RELIANCE BUY — review now"*.
   Tapping it deep-links the app to that `pending_id`.
3. **`GET /signals/pending`** — JWT-required. Returns all unexpired entries in
   `PendingStore` (order request + risk_check), same data the desktop signal card +
   risk panel show.
4. **`POST /signals/{pending_id}/confirm`** — JWT-required. Looks up the `PendingOrder`
   in the store; if missing/expired, returns 404 ("signal expired, refresh"). If found,
   calls `trade_controller.confirm_and_place(pending, dhan_client, journal_conn,
   consensus)` — **the exact same function the desktop confirm dialog calls.** Removes
   the entry from `PendingStore` on success or on risk-block (either way it's resolved).

There is intentionally **no `/prepare` endpoint reachable by the client** — preparation
happens only in the scheduler, on a fixed cadence, identically to how `app.py`'s
auto-refresh already prepares cards. The two-step guarantee is: (1) scheduler prepares
and risk-checks in the background, the client cannot skip this or influence its
inputs, and (2) the client's one call, `/confirm`, is the only way an order reaches the
broker — matching "prepare and confirm are separate calls; an order can only be placed
by `confirm_and_place`" from the existing trade_controller design, now split across a
background process and an explicit user-initiated HTTP call instead of two UI clicks.
This is at least as strict as desktop: a user cannot trigger placement without the
system having independently prepared and risk-checked that exact signal first.

Expired entries (past TTL) are dropped by `PendingStore`; confirming an expired
`pending_id` always 404s rather than silently re-preparing and placing.

---

## 5. Auth

- Supabase project, email/password, single user (your account).
- Login happens in the Android app directly against Supabase (not through this API) —
  the app gets a JWT from Supabase's own auth endpoint.
- Every API route except `GET /health` requires `Authorization: Bearer <jwt>`.
- `auth.py` verifies the JWT signature locally using Supabase's published JWKS
  (fetched at startup, no per-request network call to Supabase), and checks
  expiry/issuer. No role/permission logic needed beyond "valid token" since there is
  exactly one user.
- `POST /push/register` is how the app tells the backend which FCM token belongs to
  the logged-in device; stored in Supabase's `push_tokens` table (resourceId, user_id,
  token, updated_at).

---

## 6. Error Handling

- Dhan/API read failures (`DhanError`) → 502 with the error message; matches how
  `app.py` surfaces these in a banner today rather than crashing.
- Expired/invalid JWT → 401; app forces re-login.
- Confirming an unknown/expired `pending_id` → 404, never falls back to placing
  anything.
- Risk-blocked confirm (`risk_check.allowed is False`) → 200 with
  `ConfirmResponse(ok=False, status="BLOCKED", reasons=[...])` — same as desktop, order
  never reaches the broker, this is a normal outcome not a server error.
- FCM push failures are logged and swallowed — never affect the scheduler loop or any
  trading path.
- Scheduler tick exceptions (e.g. one instrument's data fetch fails) are caught and
  logged per-instrument so one bad symbol doesn't stop the rest of the watchlist.
- Cloudflare Tunnel or PC being offline is a client-side concern (Android spec): the
  API has no special handling for it beyond normal HTTP timeouts.

---

## 7. Testing

Same pytest style as the existing 112 tests, colocated under `tests/api/`:

- `auth.py`: valid JWT accepted; expired/malformed/missing JWT → 401; wrong signature
  → 401.
- `state.py` (`PendingStore`): entries expire after TTL; confirmed/blocked entries are
  removed; no double-confirm of the same `pending_id`.
- `routers/signals.py`: confirming a valid pending_id calls
  `trade_controller.confirm_and_place` exactly once (fake dhan_client + temp journal,
  same fixtures the existing `test_trade_controller.py` uses); confirming
  unknown/expired id returns 404 and calls nothing; risk-blocked pending_id returns
  BLOCKED and places nothing (proves no-auto-fire holds through the HTTP layer too).
- `scheduler.py`: one tick calls `signal_engine.generate` per watchlist instrument;
  non-HOLD results land in `PendingStore`; repeated ticks with the same signal don't
  re-push; a failing instrument doesn't stop others in the same tick.
- `push.py`: send_push failure doesn't raise past the caller.
- Other routers (`positions`, `reports`, `screener`, `options`, `settings`): thin
  pass-through tests confirming correct service function is called with correct args
  and its return value is serialized via the matching Pydantic schema.
- No live Supabase/FCM/Dhan calls in tests — all external calls mocked, matching the
  existing project's fixture style (`tests/conftest.py`, `tests/test_dhan_client.py`).

---

## 8. Deployment Notes

- API runs on the same PC as Streamlit, started alongside it (extend `run_app.bat` /
  `AUTOSTART.md` pattern with a second process: `uvicorn api.main:app`).
- Cloudflare Tunnel (`cloudflared`) maps a stable subdomain to the local uvicorn port;
  TLS terminates at Cloudflare. No router port-forwarding needed.
- New `.env` values: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or JWKS URL),
  `FCM_SERVICE_ACCOUNT_JSON_PATH`. Same secrets-only-in-`.env` policy as existing Dhan
  keys — never committed.
- No changes to `requirements.txt`'s existing pins; adds `fastapi`, `uvicorn`,
  `python-jose` (or `pyjwt`) for JWT verification, `httpx` for Supabase/FCM calls.

---

## 9. Out of Scope (this spec)

Android app (separate spec, next). Play Store distribution. Multi-user/multi-device
beyond one push token per login. Rate limiting / WAF hardening beyond what Cloudflare
provides by default (candidate for a later hardening pass once the app is in daily
use). Historical push notification log/inbox in-app. Changing risk limits' *values* —
`PUT /settings/risk` only exposes the existing `config_store` write path, it doesn't
change what limits exist or their defaults.
