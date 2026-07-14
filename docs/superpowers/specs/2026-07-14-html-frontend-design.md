# HTML Frontend (htmx + Jinja2) Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** all existing `services/`, `core/`, `data/` modules (unchanged); `ui/themes.chart_colors`; `services/charting`; the existing FastAPI app (`api/`); `desktop/launcher.py`.
**Replaces:** the Streamlit presentation layer (`app.py`, `pages/*`) as the primary UI. Streamlit stays in the repo during migration but the desktop launcher switches to this app.

---

## 1. Purpose

Replace the Streamlit UI with a server-rendered HTML web app (Jinja2 templates + htmx on
FastAPI), giving full design control, faster interactions, and easy hosting — without
touching any trading logic. Every page maps 1:1 to an existing Streamlit page and calls
the same `services/` functions.

**Principles:** presentation-only change — no edits to signals/risk/orders/journal; the
two-step confirm and kill-switch remain structural (enforced in `trade_controller`);
templates render, routes orchestrate, services decide; everything stays Python (no Node
build); all client assets vendored locally (no CDN — works offline and in the .exe).

**Out of scope:** the JSON `api/` routers (kept as-is for the future phone app), a
JavaScript SPA framework, real-time websockets (htmx polling is enough), removing
Streamlit files in this slice (a later cleanup once the HTML app is trusted).

---

## 2. Structure

```
web/
  __init__.py
  server.py            FastAPI sub-app (or router set) mounting HTML routes + static;
                         create_web_app() returns the app (testable, mirrors api.main).
  deps.py              request-scoped helpers reusing api/deps patterns (dhan client,
                         journal, risk config, watchlist, equity, chart colors).
  routes/
    dashboard.py       GET / ; partials: signals, confirm dialog, place, halt/resume
    reports.py         GET /reports ; P&L, equity curve, provider accuracy, cost, behavior, audit
    screener.py        GET /screener ; POST /screener/run -> results partial
    options.py         GET /options ; POST /options/build -> chain + payoff partial
    settings.py        GET /settings ; POST /settings/save
    golive.py          GET /golive ; POST /golive/gate (toggle a gate)
    btst.py            GET /btst ; scan + confirm + book
    backtest.py        GET /backtest ; POST /backtest/run -> robustness partial
  templates/
    base.html          shell: sidebar nav, theme, header, HALT banner; {% block %}
    <page>.html        one per page, extends base
    partials/*.html    htmx swap fragments (signal_cards, confirm_dialog, screener_rows,
                         payoff, backtest_result, audit_rows, error_banner, ...)
  static/
    app.css            the terminal theme + all component styles as real CSS
    htmx.min.js        vendored
    plotly.min.js      vendored (chart rendering)
    app.js             ~30 lines: init Plotly from embedded JSON, small helpers
```

The Streamlit `app.py`/`pages/*` are left in place (untouched) until the HTML app is
adopted; the desktop launcher (§7) is what actually switches the default UI.

---

## 3. Rendering model

- Each `GET /<page>` route calls the same service functions the matching Streamlit page
  calls today, builds a context dict, and returns `TemplateResponse("<page>.html", ctx)`.
- Dynamic updates use **htmx**, not full-page reloads:
  - **Dashboard signals** auto-refresh: the signals container has
    `hx-get="/partials/signals" hx-trigger="load, every 30s" hx-swap="innerHTML"`.
  - **Two-step confirm:** a card's "Select" is `hx-get="/dashboard/confirm/{sym}"` →
    returns the confirm-dialog partial (order + risk check + gap/halt warnings). Its
    "Place" button is `hx-post="/dashboard/place/{sym}"` → calls
    `trade_controller.confirm_and_place` and swaps in a result toast. **Place is the only
    route that places an order; it re-derives the pending order server-side and re-runs
    the risk gate — a single GET can never place.**
  - **HALT/Resume, Run scan, Build spread, Run backtest, Save settings, Toggle gate:**
    each is an `hx-post` returning the updated partial.
- Charts: a route builds the existing `charting` Plotly figure, passes `fig.to_json()`
  into the template as a `<script type="application/json">` block; `app.js` calls
  `Plotly.newPlot(el, JSON.parse(...))`. Colors come from `themes.chart_colors()`.

## 4. Styling

`static/app.css` ports the `terminal` theme (the approved reface look) to real CSS
variables: dark surfaces, JetBrains Mono / Outfit (self-hosted `@font-face` or system
stack), sharp corners, metric tiles with big numbers, accent-bordered signal cards, the
chip/quality styles. A theme switcher (data-attribute on `<html>`) offers the same
palettes as today. Full control means the Streamlit CSS-injection hacks disappear.

## 5. Auth / hosting

- **Local/desktop:** bound to `127.0.0.1`; no in-app login (single operator on the
  machine), same trust model as Streamlit today.
- **Hosted 24/7:** front it with Cloudflare Access (per `DEPLOY_24_7.md`); the app itself
  needs no login page. (The JSON `api/` layer keeps its JWT auth for the phone app.)

## 6. Error / edge handling

- `DhanError` in any route → render `partials/error_banner.html` inline; the rest of the
  page still renders. Matches Streamlit's current banner behavior.
- Empty data (no signals, no trades, insufficient candles) → friendly inline message, no
  blank screens.
- Kill-switch halted → dashboard shows the halted banner; Place routes refuse and return
  the HALTED result (structural gate in `trade_controller` unchanged).
- htmx request failures → a global `htmx:responseError` handler shows a small error toast.

## 7. Desktop launcher + run scripts

- `desktop/launcher.py` `_start_streamlit` is replaced by `_start_web` that runs
  `uvicorn web.server:app` headless on the free port; `wait_for_health` polls `/health`;
  pywebview opens the same native window. The `.exe` experience is identical, now HTML.
- `run_web.bat` mirrors `run_app.bat` for source runs (`uvicorn web.server:app`).
- PyInstaller spec (`desktop/build.spec`) adds `web/templates` and `web/static` to
  `datas` so the frozen app ships them.

## 8. Testing

- Each route module gets FastAPI `TestClient` tests: the page returns 200 and contains
  the expected anchors/elements; the dashboard confirm→place flow places exactly once via
  a `FakeDhan` and journals it; a GET never places; halted → HALTED and nothing placed;
  screener/backtest "run" partials render rows for injected candles; DhanError → error
  banner. (Reuses the `tests/api/conftest.py` FakeDhan + journal fixtures.)
- Service/charting logic is already fully covered; no duplication.
- Visual/interaction correctness (htmx swaps, Plotly render) verified by running.

---

## 9. Migration / rollout

Big-bang: all 8 pages built before switching the launcher default. Order of build
(each independently testable): base shell + theme → dashboard (core loop) → reports →
screener → backtest → options → settings → go-live → btst → launcher swap + packaging.
Streamlit files remain until the HTML app is confirmed working, then removed in a
follow-up cleanup slice.
