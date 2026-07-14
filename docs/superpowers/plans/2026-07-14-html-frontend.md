# HTML Frontend (htmx + Jinja2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit UI with a server-rendered HTML web app (Jinja2 + htmx on FastAPI) covering all 8 pages, without changing any trading logic.

**Architecture:** New `web/` FastAPI app serves Jinja2 templates + htmx partials; every route calls the same `services/` functions the Streamlit pages call. The safety-critical two-step confirm stays structural in `trade_controller`. Charts render client-side via vendored Plotly.js from server-built figure JSON. The desktop launcher switches from Streamlit to this app.

**Tech Stack:** FastAPI, Jinja2, htmx (vendored), Plotly.js (vendored), python-multipart, pytest TestClient. All already installed.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-html-frontend-design.md`](../specs/2026-07-14-html-frontend-design.md)

---

## Conventions for every task

- Branch `feature/html-frontend` (created). Repo-local git identity configured (plain `git commit`).
- Reuse `tests/api/conftest.py` fixtures (`fake_dhan`, `temp_journal`, `make_jwt`) — the web tests live under `tests/web/` with their own `conftest.py` importing them, OR import `FakeDhan` directly (shown per task).
- Web routes read config via `core.config_store` and services exactly like `app.py`. Never read `os.getenv` for Dhan creds (that bug is why Screener/Options broke).
- Templates use `web/templates`; static served at `/static`.
- Run the full suite (`pytest tests/ -q`) at the end of each page task; it must stay green (currently 364).

---

## Task 1: Server scaffold + base shell + theme + vendored assets

**Files:**
- Create: `web/__init__.py`, `web/routes/__init__.py`
- Create: `web/server.py`
- Create: `web/templates/base.html`
- Create: `web/static/app.css`, `web/static/app.js`
- Create: `web/static/htmx.min.js`, `web/static/plotly.min.js` (vendored)
- Test: `tests/web/__init__.py`, `tests/web/conftest.py`, `tests/web/test_server.py`

- [ ] **Step 1: Vendor the client libraries** (one-time download into static/)

Run (Git Bash):
```bash
mkdir -p web/static web/templates web/routes tests/web
curl -sL https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js -o web/static/htmx.min.js
curl -sL https://cdn.plot.ly/plotly-2.35.2.min.js -o web/static/plotly.min.js
ls -la web/static/htmx.min.js web/static/plotly.min.js
```
Expected: both files exist and are non-trivial size (htmx ~50KB, plotly ~3.5MB). If a
download fails, retry; these must be local (no CDN at runtime — CSP/offline/.exe).

- [ ] **Step 2: Write the failing test**

`tests/web/__init__.py`: (empty)

`tests/web/conftest.py`:
```python
import time
import jwt
import pytest
from core.models import OrderResult, TradeMode
from data.journal import init_db


class FakeDhan:
    def __init__(self, mode=TradeMode.PAPER):
        self.mode = mode
        self.placed = []
        self.bracket = []
        self.positions = []
        self.fund_limits = {"availabelBalance": 100000}
        self.candles_by_symbol = {}

    def place_order(self, req):
        self.placed.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="O1", exec_price=req.price)

    def place_bracket_order(self, req):
        self.bracket.append(req)
        return OrderResult(ok=True, mode=self.mode, status="FILLED",
                           dhan_order_id="BO1", exec_price=req.price)

    def get_positions(self):
        return self.positions

    def get_fund_limits(self):
        return self.fund_limits

    def get_candles(self, instrument, interval, lookback_days=5):
        return self.candles_by_symbol.get(instrument.symbol)

    def exit_position(self, instrument):
        return OrderResult(ok=True, mode=self.mode, status="PLACED",
                           dhan_order_id=f"PAPER-EXIT-{instrument.symbol}")


@pytest.fixture
def fake_dhan():
    return FakeDhan()


@pytest.fixture
def temp_journal(tmp_path):
    return init_db(str(tmp_path / "test_trades.db"))
```

`tests/web/test_server.py`:
```python
from fastapi.testclient import TestClient
from web.server import create_web_app


def test_health_ok():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_static_css_served():
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/static/app.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_base_shell_has_nav_and_htmx():
    # a trivial route rendering base with no page block still shows the nav + htmx script
    app = create_web_app()
    with TestClient(app) as c:
        r = c.get("/health")   # health is JSON; use the shell via a page later
    assert r.status_code == 200
```

- [ ] **Step 3: Write `web/server.py`**

```python
"""HTML web app: Jinja2 templates + htmx on FastAPI. Serves the same trading UI as
Streamlit, calling the same services. create_web_app() is import-safe and testable."""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))


def create_web_app() -> FastAPI:
    app = FastAPI(title="Dhan-Claude Trader (HTML)")
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    from web.routes import dashboard, reports, screener, options, settings, golive, btst, backtest
    for mod in (dashboard, reports, screener, options, settings, golive, btst, backtest):
        app.include_router(mod.router)
    return app


app = create_web_app()
```
Note: the route modules don't exist yet — for THIS task, temporarily comment out the
`from web.routes import ...` loop and the `for` loop (leave only health + static), so the
scaffold tests pass in isolation. Re-enable it in Task 2 when `dashboard` exists, adding
each module to the tuple as its task lands. (State this clearly in the commit.)

- [ ] **Step 4: Write `web/templates/base.html`**

```html
<!doctype html>
<html lang="en" data-theme="terminal">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Dhan-Claude Trader{% endblock %}</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/htmx.min.js" defer></script>
  <script src="/static/plotly.min.js" defer></script>
  <script src="/static/app.js" defer></script>
</head>
<body>
  <nav class="sidebar">
    <div class="brand">Dhan-Claude</div>
    <a href="/">Dashboard</a><a href="/reports">Reports</a><a href="/screener">Screener</a>
    <a href="/backtest">Backtest</a><a href="/options">Options</a><a href="/btst">BTST</a>
    <a href="/settings">Settings</a><a href="/golive">Go-Live</a>
  </nav>
  <main class="content">
    {% block halt_banner %}{% endblock %}
    {% block body %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 5: Write `web/static/app.css`** (port the terminal theme; full base + components)

```css
:root{--bg:#0e1117;--surface:#141a24;--surface2:#1c2436;--border:#232936;--ink:#e6e9ef;
  --muted:#6b7280;--green:#34d399;--signal:#f0999a;--gold:#fbbf24;--accent:#5dcaa5;
  --mono:ui-monospace,"Cascadia Mono",Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",sans-serif;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--mono);display:flex}
a{color:var(--accent);text-decoration:none}
.sidebar{width:150px;min-height:100vh;background:#0b0f16;border-right:1px solid var(--border);
  padding:14px 10px;display:flex;flex-direction:column;gap:6px}
.sidebar .brand{font-family:var(--sans);font-weight:600;margin-bottom:10px}
.sidebar a{padding:6px 8px;font-size:13px;border-radius:0}
.sidebar a:hover{background:var(--surface)}
.content{flex:1;padding:16px 22px;max-width:1100px}
h1,h2,h3{font-family:var(--sans);font-weight:600;letter-spacing:-.01em}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--border);padding:10px 12px}
.tile .label{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.tile .num{font-size:22px;font-weight:500;margin-top:3px}
.num.g{color:var(--green)}.num.r{color:var(--signal)}
.card{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--muted);
  padding:10px 14px;margin-bottom:8px}
.card.buy{border-left-color:var(--green)}.card.sell{border-left-color:var(--signal)}
.card.hold{border-left-color:var(--gold)}
.conf{font-size:20px;font-weight:500;font-family:var(--mono)}
.conf.buy{color:var(--green)}.conf.sell{color:var(--signal)}.conf.hold{color:var(--gold)}
.muted{color:var(--muted);font-size:12px}
.chip{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;background:var(--surface2);
  color:#85b7eb;margin-right:4px}
.chip.q{background:#12261e;color:var(--green)}.chip.qlow{background:#2a1f1f;color:var(--gold)}
button,.btn{font-family:var(--sans);font-size:12px;font-weight:600;padding:6px 13px;
  background:var(--ink);color:var(--bg);border:1px solid var(--ink);cursor:pointer}
button:hover{background:var(--accent);border-color:var(--accent);color:#04342c}
button.go{background:var(--green);border-color:var(--green);color:#04342c}
button.halt{background:#3a1214;border-color:#5a2327;color:#ff9ba0}
.banner{padding:9px 12px;font-family:var(--sans);font-size:13px;margin-bottom:10px}
.banner.halt{background:#3a1214;border:1px solid #5a2327;color:#ff9ba0}
.banner.warn{background:#2a2410;border:1px solid #4a3f18;color:var(--gold)}
.banner.ok{background:#0f2620;border:1px solid #1d4a3c;color:var(--green)}
.banner.err{background:#3a1214;border:1px solid #5a2327;color:#ff9ba0}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{border:1px solid var(--border);padding:4px 8px;text-align:left}
th{color:var(--muted);font-weight:500}
.chart{width:100%;height:320px}
input,select{background:var(--surface);border:1px solid var(--border);color:var(--ink);
  padding:6px 8px;font-family:var(--mono)}
#toast{position:static;margin:8px 0}
@media(max-width:640px){body{flex-direction:column}.sidebar{width:100%;flex-direction:row;
  flex-wrap:wrap;min-height:auto}.tiles{grid-template-columns:repeat(2,1fr)}}
```

- [ ] **Step 6: Write `web/static/app.js`**

```javascript
// Render any Plotly figures embedded as <script type="application/json" class="plotly-fig" data-target="id">
function renderPlots(root){
  (root||document).querySelectorAll('script.plotly-fig').forEach(function(s){
    try{
      var fig = JSON.parse(s.textContent);
      var el = document.getElementById(s.dataset.target);
      if(el && window.Plotly){ Plotly.newPlot(el, fig.data||[], fig.layout||{}, {displayModeBar:false, responsive:true}); }
    }catch(e){ console.error('plot render failed', e); }
  });
}
document.addEventListener('DOMContentLoaded', function(){ renderPlots(document); });
document.body.addEventListener('htmx:afterSwap', function(ev){ renderPlots(ev.target); });
document.body.addEventListener('htmx:responseError', function(){
  var t=document.getElementById('toast'); if(t){ t.innerHTML='<div class="banner err">Request failed — retry.</div>'; }
});
```

- [ ] **Step 7: Run tests + commit**

Run: `pytest tests/web/test_server.py -q`  → Expected: 3 passed
Run: `pytest tests/ -q`  → Expected: 364 + 3 still green.
```bash
git add web/ tests/web/
git commit -m "feat(web): FastAPI HTML scaffold — base shell, terminal-theme CSS, vendored htmx+plotly"
```

---

## Task 2: Web deps (shared route helpers)

**Files:**
- Create: `web/deps.py`
- Test: `tests/web/test_web_deps.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_web_deps.py`:
```python
import json
from core.models import Instrument
from web import deps


def test_load_watchlist_reads_file(tmp_path):
    p = tmp_path / "watchlist.json"
    p.write_text(json.dumps({"instruments": [
        {"symbol": "RELIANCE", "exchange_segment": "NSE_EQ", "security_id": "2885",
         "lot_size": 1, "kind": "EQUITY"}]}))
    wl = deps.load_watchlist(path=p)
    assert wl == [Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                             security_id="2885", lot_size=1, kind="EQUITY")]


def test_get_equity_paper_uses_account_capital(monkeypatch, tmp_path):
    from core import config_store
    monkeypatch.setattr(config_store, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, tmp_path / "s.json"))
    monkeypatch.setenv("ACCOUNT_CAPITAL", "150000")
    assert deps.get_equity("PAPER", None) == 150000.0


def test_style_for():
    assert deps.style_for("INDEX") == "intraday"
    assert deps.style_for("EQUITY") == "positional"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/web/test_web_deps.py -v` → FAIL (no `web.deps`).

- [ ] **Step 3: Write `web/deps.py`**

```python
"""Shared helpers for web routes — mirror the wiring app.py does, reading creds from
config_store (never os.getenv). Daily lookback is 400 so the engine has enough bars."""
from __future__ import annotations
import json
from pathlib import Path

from core import config_store
from core.models import Instrument, TradeMode
from data.journal import init_db
from services import instruments, risk_manager
from services.dhan_client import DhanClient, DhanError

_journal = None
_index: dict | None = None


def get_journal():
    global _journal
    if _journal is None:
        _journal = init_db("trades.db")
    return _journal


def get_mode() -> str:
    return config_store.get_setting("TRADE_MODE", "PAPER")


def get_dhan(mode: str | None = None) -> DhanClient:
    mode = mode or get_mode()
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


def get_risk_config():
    return risk_manager.load_risk_config({
        "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
        "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
        "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
    })


def _instrument_index() -> dict:
    global _index
    if _index is not None:
        return _index
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
               else instruments.download_master())
        _index = instruments.build_index(text)
    except Exception:                              # noqa: BLE001
        _index = {}
    return _index


def load_watchlist(path: str | Path = "watchlist.json") -> list[Instrument]:
    data = json.loads(Path(path).read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY")) for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, _instrument_index())


def get_equity(mode: str, dhan) -> float:
    if mode == "LIVE":
        try:
            f = dhan.get_fund_limits()
            return float(f.get("availabelBalance", f.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


def style_for(kind: str) -> str:
    return "intraday" if kind in ("INDEX", "FUT", "OPT") else "positional"


def candles_for(dhan, instr):
    style = style_for(instr.kind)
    return dhan.get_candles(instr, interval=15 if style == "intraday" else "day",
                            lookback_days=10 if style == "intraday" else 400)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/web/test_web_deps.py -v` → 3 passed.

- [ ] **Step 5: Commit**
```bash
git add web/deps.py tests/web/test_web_deps.py
git commit -m "feat(web): shared route helpers (config_store creds, 400-day lookback)"
```

---

## Task 3: Dashboard — page + signals partial (read path)

**Files:**
- Create: `web/routes/dashboard.py`
- Create: `web/templates/dashboard.html`, `web/templates/partials/signals.html`, `web/templates/partials/error_banner.html`
- Modify: `web/server.py` (enable the dashboard import)
- Test: `tests/web/test_dashboard.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_dashboard.py`:
```python
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from core.models import Instrument
from web.server import create_web_app
from web.routes import dashboard as dash
import web.deps as wdeps


def _candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan, temp_journal, watchlist):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": watchlist)
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(dash, "kill_switch", type("K", (), {"is_halted": staticmethod(lambda: False)}))
    return TestClient(create_web_app())


def test_dashboard_page_renders(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])
    r = c.get("/")
    assert r.status_code == 200
    assert "Dhan-Claude" in r.text
    assert "Today P&amp;L" in r.text or "Today P&L" in r.text


def test_signals_partial_lists_instruments(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])
    r = c.get("/partials/signals")
    assert r.status_code == 200
    assert "RELIANCE" in r.text


def test_signals_partial_shows_insufficient_when_no_candles(monkeypatch, fake_dhan, temp_journal):
    instr = Instrument(symbol="ZZZ", exchange_segment="NSE_EQ", security_id="9")
    c = _client(monkeypatch, fake_dhan, temp_journal, [instr])   # no candles registered
    r = c.get("/partials/signals")
    assert r.status_code == 200
    assert "insufficient" in r.text.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/web/test_dashboard.py -v` → FAIL (no `web.routes.dashboard`).

- [ ] **Step 3: Write `web/routes/dashboard.py`** (read path; confirm/place added in Task 4)

```python
"""Dashboard routes — risk panel + live signal cards, mirroring app.py's signal loop.
Read-only here; the two-step confirm/place lives in Task 4 (same file, appended)."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.models import SignalType, TradeMode
from data.journal import to_legs
from services import indicators as ind
from services import risk_manager, signal_engine, kill_switch
from services.dhan_client import DhanError
from services.quality_gate import apply_gate
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.server import templates

router = APIRouter()


def _risk_panel(mode, dhan, journal, cfg):
    legs = to_legs(journal, mode=mode)
    try:
        dpnl = risk_manager.day_pnl(TradeMode(mode), dhan_client=dhan, legs=legs,
                                    ltp_fn=lambda s: None)
        open_count = risk_manager.open_position_count(TradeMode(mode), dhan_client=dhan,
                                                      legs=legs)
        err = None
    except DhanError as e:
        dpnl, open_count, err = 0.0, 0, str(e)
    buffer = max(0.0, cfg.max_daily_loss + dpnl)
    blocked = dpnl <= -cfg.max_daily_loss or open_count >= cfg.max_open_positions
    return {"dpnl": dpnl, "open_count": open_count, "buffer": buffer,
            "blocked": blocked, "err": err}


def _build_cards(mode, dhan, cfg, panel):
    cards = []
    for instr in deps.load_watchlist():
        try:
            candles = deps.candles_for(dhan, instr)
            if candles is None or len(candles) < 30:
                cards.append({"symbol": instr.symbol, "insufficient": True})
                continue
            style = deps.style_for(instr.kind)
            snap = build_confluence(candles, regime=None, style=style,
                                    active_ids=list(range(1, 30)))
            last = float(candles["close"].iloc[-1])
            atr = float(ind.atr(candles).dropna().iloc[-1])
            cs = signal_engine.generate(instr, snap, last_price=last, atr=atr,
                                        mode="mock", cache={})
            gate = apply_gate(cs, fundamentals={}, event_flags=[], kind=instr.kind)
            sd = cs.indicator_snapshot
            cards.append({
                "symbol": instr.symbol, "regime": snap.regime.value,
                "signal": cs.consensus.value, "cls": cs.consensus.value.lower(),
                "conf": cs.avg_confidence, "agree": cs.agreement_pct,
                "entry": sd.get("entry"), "sl": sd.get("stop_loss"), "tgt": sd.get("target"),
                "quality": gate.score, "qlabel": "PASS" if gate.passed else ("VETO" if gate.vetoed else "LOW"),
                "qpass": gate.passed,
                "selectable": cs.consensus is not SignalType.HOLD and gate.passed and not panel["blocked"],
                "insufficient": False})
        except DhanError as e:
            cards.append({"symbol": instr.symbol, "error": str(e)})
    return cards


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    panel = _risk_panel(mode, dhan, deps.get_journal(), cfg)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "mode": mode, "panel": panel, "cfg": cfg,
        "halted": kill_switch.is_halted()})


@router.get("/partials/signals", response_class=HTMLResponse)
def signals_partial(request: Request):
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    panel = _risk_panel(mode, dhan, deps.get_journal(), cfg)
    cards = _build_cards(mode, dhan, cfg, panel)
    return templates.TemplateResponse("partials/signals.html",
                                      {"request": request, "cards": cards})
```

- [ ] **Step 4: Write the templates**

`web/templates/partials/error_banner.html`:
```html
<div class="banner err">{{ message }}</div>
```

`web/templates/partials/signals.html`:
```html
{% for c in cards %}
  {% if c.insufficient %}
    <div class="card"><b>{{ c.symbol }}</b> <span class="muted">insufficient candle data</span></div>
  {% elif c.error %}
    <div class="card"><b>{{ c.symbol }}</b> <span class="muted">data error: {{ c.error }}</span></div>
  {% else %}
    <div class="card {{ c.cls }}">
      <b>{{ c.symbol }}</b> <span class="muted">{{ c.regime }}</span>
      <span class="conf {{ c.cls }}">{{ c.signal }} {{ c.conf }}%</span>
      <span class="muted">agree {{ c.agree }}%</span>
      <span class="chip {{ 'q' if c.qpass else 'qlow' }}">Quality {{ c.quality }} {{ c.qlabel }}</span>
      <div class="muted">entry {{ c.entry }} · SL {{ c.sl }} · tgt {{ c.tgt }}</div>
      {% if c.selectable %}
        <button class="go" hx-get="/dashboard/confirm/{{ c.symbol }}" hx-target="#dialog" hx-swap="innerHTML">Select {{ c.symbol }} →</button>
      {% endif %}
    </div>
  {% endif %}
{% else %}
  <div class="muted">No instruments in watchlist.</div>
{% endfor %}
```

`web/templates/dashboard.html`:
```html
{% extends "base.html" %}
{% block title %}Dashboard — Dhan-Claude Trader{% endblock %}
{% block halt_banner %}{% if halted %}<div class="banner halt">🔴 TRADING HALTED — no orders will be placed. <button class="go" hx-post="/dashboard/resume" hx-target="body" hx-swap="none" hx-on::after-request="location.reload()">Resume</button></div>{% endif %}{% endblock %}
{% block body %}
<h2>Dashboard <span class="muted">{{ '🟡 PAPER' if mode=='PAPER' else '🔴 LIVE' }}</span></h2>
<div style="display:flex;gap:8px;margin:8px 0">
  {% if not halted %}<button class="halt" hx-post="/dashboard/halt" hx-target="body" hx-swap="none" hx-on::after-request="location.reload()">🔴 HALT trading</button>{% endif %}
</div>
{% if panel.err %}<div class="banner err">Dhan read failed: {{ panel.err }}</div>{% endif %}
<div class="tiles">
  <div class="tile"><div class="label">Today P&L</div><div class="num {{ 'g' if panel.dpnl>=0 else 'r' }}">₹{{ '%.0f'|format(panel.dpnl) }}</div></div>
  <div class="tile"><div class="label">Loss buffer</div><div class="num">₹{{ '%.0f'|format(panel.buffer) }}</div></div>
  <div class="tile"><div class="label">Open positions</div><div class="num">{{ panel.open_count }}/{{ cfg.max_open_positions }}</div></div>
  <div class="tile"><div class="label">Orders</div><div class="num {{ 'r' if panel.blocked else 'g' }}">{{ '🔴 blocked' if panel.blocked else '✓ allowed' }}</div></div>
</div>
{% if panel.blocked %}<div class="banner warn">New orders blocked: risk limit reached.</div>{% endif %}
<h3>Live signals</h3>
<div id="signals" hx-get="/partials/signals" hx-trigger="load, every 30s" hx-swap="innerHTML">
  <div class="muted">Loading signals…</div>
</div>
<div id="dialog"></div>
<div id="toast"></div>
{% endblock %}
```

- [ ] **Step 5: Enable the dashboard route in `web/server.py`**

Replace the temporary health-only import block with:
```python
    from web.routes import dashboard
    app.include_router(dashboard.router)
```
(Other route modules are added to this list as their tasks land — Tasks 4–10.)

- [ ] **Step 6: Run tests + commit**

Run: `pytest tests/web/test_dashboard.py -v` → 3 passed.
Run: `pytest tests/ -q` → green.
```bash
git add web/routes/dashboard.py web/templates/ web/server.py tests/web/test_dashboard.py
git commit -m "feat(web): dashboard page + auto-refreshing signals partial"
```

---

## Task 4: Dashboard — two-step confirm + place + halt (safety-critical)

**Files:**
- Modify: `web/routes/dashboard.py` (append routes)
- Create: `web/templates/partials/confirm_dialog.html`, `web/templates/partials/place_result.html`
- Test: `tests/web/test_dashboard_confirm.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_dashboard_confirm.py`:
```python
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from core.models import Instrument
from web.server import create_web_app
from web.routes import dashboard as dash
import web.deps as wdeps


def _candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan, temp_journal, halted=False):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(dash, "kill_switch",
                        type("K", (), {"is_halted": staticmethod(lambda: halted)}))
    return TestClient(create_web_app()), fake_dhan


def test_confirm_returns_dialog(monkeypatch, fake_dhan, temp_journal):
    c, _ = _client(monkeypatch, fake_dhan, temp_journal)
    r = c.get("/dashboard/confirm/RELIANCE")
    assert r.status_code == 200
    assert "Place" in r.text and "RELIANCE" in r.text


def test_get_confirm_does_not_place(monkeypatch, fake_dhan, temp_journal):
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal)
    c.get("/dashboard/confirm/RELIANCE")
    assert dhan.placed == [] and dhan.bracket == []   # a GET never places


def test_place_places_order_and_journals(monkeypatch, fake_dhan, temp_journal):
    from data.journal import list_trades
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal)
    r = c.post("/dashboard/place/RELIANCE")
    assert r.status_code == 200
    assert (len(dhan.placed) + len(dhan.bracket)) == 1
    assert len(list_trades(temp_journal)) == 1


def test_place_refused_when_halted(monkeypatch, fake_dhan, temp_journal):
    c, dhan = _client(monkeypatch, fake_dhan, temp_journal, halted=True)
    r = c.post("/dashboard/place/RELIANCE")
    assert r.status_code == 200
    assert "HALTED" in r.text.upper()
    assert dhan.placed == [] and dhan.bracket == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/web/test_dashboard_confirm.py -v` → FAIL (routes missing).

- [ ] **Step 3: Append to `web/routes/dashboard.py`**

```python
from fastapi import HTTPException
from services import trade_controller
from services.quality_gate import apply_gate as _apply_gate
from services.sizing import quality_multiplier


def _prepare_for(symbol: str):
    """Re-derive the pending order server-side for `symbol` from fresh candles.
    Returns (instrument, consensus, gate, pending, panel, mode, dhan, journal) or None."""
    mode = deps.get_mode()
    dhan = deps.get_dhan(mode)
    cfg = deps.get_risk_config()
    journal = deps.get_journal()
    panel = _risk_panel(mode, dhan, journal, cfg)
    instr = next((i for i in deps.load_watchlist() if i.symbol == symbol), None)
    if instr is None:
        return None
    candles = deps.candles_for(dhan, instr)
    if candles is None or len(candles) < 30:
        return None
    style = deps.style_for(instr.kind)
    snap = build_confluence(candles, regime=None, style=style, active_ids=list(range(1, 30)))
    last = float(candles["close"].iloc[-1])
    atr = float(ind.atr(candles).dropna().iloc[-1])
    cs = signal_engine.generate(instr, snap, last_price=last, atr=atr, mode="mock", cache={})
    gate = _apply_gate(cs, fundamentals={}, event_flags=[], kind=instr.kind)
    equity = deps.get_equity(mode, dhan)
    pending = trade_controller.prepare_order(cs, instr, equity=equity, cfg=cfg,
                                             day_pnl_value=panel["dpnl"],
                                             open_count=panel["open_count"])
    mult = min(1.0, quality_multiplier(gate.score))
    if mult < 1.0:
        pending.order_request.qty = max(1, int(pending.order_request.qty * mult))
    return instr, cs, gate, pending, panel, mode, dhan, journal


@router.get("/dashboard/confirm/{symbol}", response_class=HTMLResponse)
def confirm(request: Request, symbol: str):
    got = _prepare_for(symbol)
    if got is None:
        raise HTTPException(404, "signal unavailable")
    instr, cs, gate, pending, panel, *_ = got
    req = pending.order_request
    return templates.TemplateResponse("partials/confirm_dialog.html", {
        "request": request, "symbol": symbol, "req": req,
        "rc": pending.risk_check, "halted": kill_switch.is_halted(),
        "gate_pass": gate.passed})


@router.post("/dashboard/place/{symbol}", response_class=HTMLResponse)
def place(request: Request, symbol: str):
    if kill_switch.is_halted():
        return templates.TemplateResponse("partials/place_result.html",
                                          {"request": request, "status": "HALTED",
                                           "ok": False, "symbol": symbol})
    got = _prepare_for(symbol)
    if got is None:
        raise HTTPException(404, "signal unavailable")
    instr, cs, gate, pending, panel, mode, dhan, journal = got
    res = trade_controller.confirm_and_place(pending, dhan_client=dhan,
                                             journal_conn=journal, consensus=cs)
    return templates.TemplateResponse("partials/place_result.html", {
        "request": request, "status": res.status, "ok": res.ok, "symbol": symbol})


@router.post("/dashboard/halt", response_class=HTMLResponse)
def halt(request: Request):
    kill_switch.halt("manual halt from web dashboard")
    return HTMLResponse("")


@router.post("/dashboard/resume", response_class=HTMLResponse)
def resume(request: Request):
    kill_switch.resume()
    return HTMLResponse("")
```

- [ ] **Step 4: Write the partials**

`web/templates/partials/confirm_dialog.html`:
```html
<div class="banner warn">⚠ Confirm order — step 2 of 2</div>
<div class="card {{ req.side.value.lower() }}">
  <b>{{ symbol }}</b> {{ req.side.value }} {{ req.qty }} @ ₹{{ req.price }}
  <span class="muted">({{ req.product_type }})</span>
  {% if rc.allowed %}<div class="banner ok">Risk check ✅ passed</div>
  {% else %}<div class="banner err">Blocked: {{ rc.reasons|join('; ') }}</div>{% endif %}
  {% if halted %}<div class="banner halt">🔴 Halted — resume to place.</div>{% endif %}
  <div style="display:flex;gap:8px;margin-top:8px">
    <button class="go" hx-post="/dashboard/place/{{ symbol }}" hx-target="#toast" hx-swap="innerHTML"
            {% if not rc.allowed or halted %}disabled{% endif %}>✓ Place order</button>
    <button hx-get="/partials/blank" hx-target="#dialog" hx-swap="innerHTML" onclick="document.getElementById('dialog').innerHTML=''">Cancel</button>
  </div>
</div>
```

`web/templates/partials/place_result.html`:
```html
<div class="banner {{ 'ok' if ok else 'err' }}">{{ symbol }}: {{ status }}</div>
```

Add a tiny blank route so Cancel works cleanly — append to `dashboard.py`:
```python
@router.get("/partials/blank", response_class=HTMLResponse)
def blank():
    return HTMLResponse("")
```

- [ ] **Step 5: Run tests + commit**

Run: `pytest tests/web/test_dashboard_confirm.py -v` → 4 passed.
Run: `pytest tests/ -q` → green.
```bash
git add web/routes/dashboard.py web/templates/partials/
git commit -m "feat(web): dashboard two-step confirm + place (structural gate) + halt/resume"
```

---

## Task 5: Charts helper (Plotly figure → template JSON)

**Files:**
- Create: `web/charts.py`
- Test: `tests/web/test_web_charts.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_web_charts.py`:
```python
import json
from web import charts


def test_fig_json_is_valid_json_with_data_and_layout():
    from core.models import RealizedTrade
    rt = RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
                       buy_price=100, sell_price=110, gross_pnl=10, charges=0, net_pnl=10,
                       rr_predicted=None, rr_achieved=None,
                       opened_at="2026-07-01T09:00:00", closed_at="2026-07-01T15:00:00")
    from services import charting
    fig = charting.equity_curve([rt] * 3)
    s = charts.fig_json(fig)
    parsed = json.loads(s)
    assert "data" in parsed and "layout" in parsed
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/web/test_web_charts.py -v` → FAIL (no `web.charts`).

- [ ] **Step 3: Write `web/charts.py`**

```python
"""Serialize a Plotly figure to JSON for the template. app.js parses the embedded
JSON and calls Plotly.newPlot client-side (Plotly.js is vendored in static/)."""
from __future__ import annotations
import plotly.io as pio


def fig_json(fig) -> str:
    return pio.to_json(fig)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/web/test_web_charts.py -v` → 1 passed.

- [ ] **Step 5: Commit**
```bash
git add web/charts.py tests/web/test_web_charts.py
git commit -m "feat(web): Plotly figure -> JSON helper for client-side render"
```

Usage pattern for any page embedding a chart (reference for later tasks):
```html
<div id="equity" class="chart"></div>
<script type="application/json" class="plotly-fig" data-target="equity">{{ equity_json|safe }}</script>
```
where the route passes `equity_json=charts.fig_json(charting.equity_curve(trades, colors))`.

---

## Task 6: Reports page

**Files:**
- Create: `web/routes/reports.py`, `web/templates/reports.html`
- Modify: `web/server.py` (add reports to the import list)
- Test: `tests/web/test_reports.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_reports.py`:
```python
from fastapi.testclient import TestClient
from web.server import create_web_app
from web.routes import reports as rep
import web.deps as wdeps
from data.journal import log_order
from core.models import Instrument, OrderRequest, OrderResult, OrderType, Side, TradeMode


def _client(monkeypatch, temp_journal):
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_reports_renders_pnl_and_sections(monkeypatch, temp_journal):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    req = OrderRequest(instrument=instr, side=Side.BUY, order_type=OrderType.MARKET, qty=10, price=100.0)
    log_order(temp_journal, req, OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
              dhan_order_id="O1", exec_price=100.0))
    c = _client(monkeypatch, temp_journal)
    r = c.get("/reports")
    assert r.status_code == 200
    assert "Equity curve" in r.text
    assert "AI cost" in r.text
    assert "Audit ledger" in r.text
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/web/test_reports.py -v` → FAIL.

- [ ] **Step 3: Write `web/routes/reports.py`**

```python
"""Reports page — P&L, equity curve, provider accuracy, AI cost, behavior, audit."""
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from data.journal import to_legs
from services import behavior, charting, audit, cost
from services.accounting import pnl_statement, realized_trades
from services.eod_report import build_report
from ui import themes
from web import deps, charts
from web.server import templates

router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request, mode: str = "PAPER"):
    journal = deps.get_journal()
    legs = to_legs(journal, mode=mode)
    stmt = pnl_statement(legs, mode=mode, period="all", period_key=None, ltp_fn=lambda s: None)
    trades = realized_trades(legs, mode=mode)
    cc = themes.chart_colors()
    disp = behavior.disposition_effect(trades)
    rep = build_report(journal, mode=mode)
    runs = cost.read_runs()
    return templates.TemplateResponse("reports.html", {
        "request": request, "mode": mode, "stmt": asdict(stmt),
        "equity_json": charts.fig_json(charting.equity_curve(trades, colors=cc)),
        "accuracy_json": charts.fig_json(charting.provider_accuracy(rep.get("leaderboard", []), colors=cc)),
        "disp": disp, "cost_today": cost.summary(runs, "day"),
        "cost_month": cost.summary(runs, "month"),
        "audit": audit.read_events(limit=50)})
```

- [ ] **Step 4: Write `web/templates/reports.html`**

```html
{% extends "base.html" %}
{% block title %}Reports — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>Reports & Accounting <span class="muted">{{ mode }}</span></h2>
<div class="tiles" style="grid-template-columns:repeat(3,1fr)">
  <div class="tile"><div class="label">Net realized</div><div class="num g">₹{{ '%.2f'|format(stmt.net_realized) }}</div></div>
  <div class="tile"><div class="label">Unrealized</div><div class="num">₹{{ '%.2f'|format(stmt.unrealized) }}</div></div>
  <div class="tile"><div class="label">Total P&L</div><div class="num">₹{{ '%.2f'|format(stmt.total_pnl) }}</div></div>
</div>
<h3>Equity curve</h3>
<div id="equity" class="chart"></div>
<script type="application/json" class="plotly-fig" data-target="equity">{{ equity_json|safe }}</script>
<h3>Provider accuracy</h3>
<div id="accuracy" class="chart" style="height:220px"></div>
<script type="application/json" class="plotly-fig" data-target="accuracy">{{ accuracy_json|safe }}</script>
<h3>🧠 Behavior — disposition effect</h3>
<div class="banner {{ 'warn' if disp.present else 'ok' }}">{{ disp.verdict }}</div>
<h3>💸 AI cost</h3>
<p class="muted">Today ₹{{ '%.2f'|format(cost_today.total_cost) }} · This month ₹{{ '%.2f'|format(cost_month.total_cost) }}</p>
<h3>🧾 Audit ledger</h3>
<table><tr><th>ts</th><th>event</th><th>detail</th></tr>
{% for e in audit %}<tr><td>{{ e.ts }}</td><td>{{ e.event }}</td><td>{{ e.detail }}</td></tr>{% endfor %}
{% if not audit %}<tr><td colspan="3" class="muted">No audit events yet.</td></tr>{% endif %}
</table>
{% endblock %}
```

- [ ] **Step 5: Add `reports` to `web/server.py`** import list:
```python
    from web.routes import dashboard, reports
    for mod in (dashboard, reports):
        app.include_router(mod.router)
```

- [ ] **Step 6: Run tests + commit**

Run: `pytest tests/web/test_reports.py -v` → 1 passed. Then `pytest tests/ -q` → green.
```bash
git add web/routes/reports.py web/templates/reports.html web/server.py tests/web/test_reports.py
git commit -m "feat(web): reports page (P&L, equity curve, accuracy, cost, behavior, audit)"
```

---

## Task 7: Screener page

**Files:**
- Create: `web/routes/screener.py`, `web/templates/screener.html`, `web/templates/partials/screener_rows.html`
- Modify: `web/server.py`
- Test: `tests/web/test_screener_web.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_screener_web.py`:
```python
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from core.models import Instrument
from web.server import create_web_app
import web.deps as wdeps


def _candles(n=250):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 40, n) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": close, "high": close+1, "low": close-1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _candles()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_screener_page_renders(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.get("/screener")
    assert r.status_code == 200 and "Run scan" in r.text


def test_screener_run_returns_rows(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.post("/screener/run")
    assert r.status_code == 200 and "RELIANCE" in r.text
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write `web/routes/screener.py`**

```python
"""Screener page — ranked setups across the watchlist via services.screener.scan."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.screener import scan
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/screener", response_class=HTMLResponse)
def screener(request: Request):
    return templates.TemplateResponse("screener.html", {"request": request})


@router.post("/screener/run", response_class=HTMLResponse)
def run(request: Request):
    dhan = deps.get_dhan()
    rows = scan(deps.load_watchlist(), candles_fn=lambda i: deps.candles_for(dhan, i),
                active_ids=list(range(1, 30)), signals_only=False)
    return templates.TemplateResponse("partials/screener_rows.html",
                                      {"request": request, "rows": rows})
```

- [ ] **Step 4: Templates**

`web/templates/screener.html`:
```html
{% extends "base.html" %}
{% block title %}Screener — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>🔍 Strategy Screener</h2>
<button hx-post="/screener/run" hx-target="#rows" hx-swap="innerHTML" hx-indicator="#si">Run scan</button>
<span id="si" class="htmx-indicator muted"> scanning…</span>
<div id="rows"></div>
{% endblock %}
```

`web/templates/partials/screener_rows.html`:
```html
<table><tr><th>Symbol</th><th>Regime</th><th>Signal</th><th>Net</th><th>Buy/Sell/Hold</th></tr>
{% for r in rows %}
  {% if r.error %}<tr><td>{{ r.symbol }}</td><td colspan="4" class="muted">{{ r.error }}</td></tr>
  {% else %}<tr><td>{{ r.symbol }}</td><td>{{ r.regime }}</td>
    <td class="{{ r.signal|lower }}">{{ r.signal }}</td><td>{{ '%.3f'|format(r.net_score) }}</td>
    <td>{{ r.buy }}/{{ r.sell }}/{{ r.hold }}</td></tr>{% endif %}
{% else %}<tr><td colspan="5" class="muted">No results.</td></tr>{% endfor %}
</table>
```

- [ ] **Step 5: Add `screener` to server import list** (extend the tuple: `dashboard, reports, screener`).

- [ ] **Step 6: Run tests + commit**

Run: `pytest tests/web/test_screener_web.py -v` → 2 passed. `pytest tests/ -q` → green.
```bash
git add web/routes/screener.py web/templates/screener.html web/templates/partials/screener_rows.html web/server.py tests/web/test_screener_web.py
git commit -m "feat(web): screener page with run-scan partial"
```

---

## Task 8: Backtest page

**Files:**
- Create: `web/routes/backtest.py`, `web/templates/backtest.html`, `web/templates/partials/backtest_result.html`
- Modify: `web/server.py`
- Test: `tests/web/test_backtest_web.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_backtest_web.py`:
```python
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from core.models import Instrument
from web.server import create_web_app
import web.deps as wdeps


def _trend(n=1400):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 120, n) + rng.normal(0, 1.0, n)
    return pd.DataFrame({"open": np.concatenate([[close[0]], close[:-1]]),
                         "high": close+1, "low": close-1, "close": close,
                         "volume": rng.uniform(1000, 5000, n)})


def _client(monkeypatch, fake_dhan):
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    fake_dhan.candles_by_symbol["RELIANCE"] = _trend()
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [instr])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    return TestClient(create_web_app())


def test_backtest_page_renders(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.get("/backtest")
    assert r.status_code == 200 and "Run backtest" in r.text


def test_backtest_run_returns_result_or_insufficient(monkeypatch, fake_dhan):
    c = _client(monkeypatch, fake_dhan)
    r = c.post("/backtest/run", data={"symbol": "RELIANCE", "style": "positional"})
    assert r.status_code == 200
    assert ("robust" in r.text.lower()) or ("insufficient" in r.text.lower())
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write `web/routes/backtest.py`**

```python
"""Backtest page — simulate + walk-forward / Monte-Carlo / bootstrap robustness verdict."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from services import backtest, backtest_robust
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/backtest", response_class=HTMLResponse)
def page(request: Request):
    syms = [i.symbol for i in deps.load_watchlist()] or ["NIFTY"]
    return templates.TemplateResponse("backtest.html", {"request": request, "syms": syms})


@router.post("/backtest/run", response_class=HTMLResponse)
def run(request: Request, symbol: str = Form(...), style: str = Form("positional")):
    dhan = deps.get_dhan()
    instr = next((i for i in deps.load_watchlist() if i.symbol == symbol), None)
    ctx = {"request": request, "result": None, "verdict": None, "wf": None, "mc": None, "ci": None}
    if instr is None:
        return templates.TemplateResponse("partials/backtest_result.html", ctx)
    candles = deps.candles_for(dhan, instr) if style != "positional" else \
        dhan.get_candles(instr, interval="day", lookback_days=365)
    seg = "equity_intraday" if style == "intraday" else "equity_delivery"
    sim_kw = {"active_ids": list(range(1, 30)), "style": style, "segment": seg, "warmup": 200}
    result = backtest.simulate(candles, **sim_kw)
    if result.n_trades < 10:
        ctx["insufficient"] = result.n_trades
        return templates.TemplateResponse("partials/backtest_result.html", ctx)
    wf = backtest_robust.walk_forward(candles, n_splits=4, sim_kwargs=sim_kw)
    mc = backtest_robust.monte_carlo_drawdown(result)
    ci = backtest_robust.bootstrap_ci(result)
    ctx.update({"result": result, "verdict": backtest_robust.robustness_verdict(wf, mc, ci),
                "wf": wf, "mc": mc, "ci": ci})
    return templates.TemplateResponse("partials/backtest_result.html", ctx)
```

- [ ] **Step 4: Templates**

`web/templates/backtest.html`:
```html
{% extends "base.html" %}
{% block title %}Backtest — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>Backtest & robustness</h2>
<p class="muted">Validate an edge before trusting capital. Reduces curve-fit risk — never zero.</p>
<form hx-post="/backtest/run" hx-target="#result" hx-swap="innerHTML">
  <select name="symbol">{% for s in syms %}<option>{{ s }}</option>{% endfor %}</select>
  <select name="style"><option>positional</option><option>intraday</option></select>
  <button type="submit">Run backtest</button>
</form>
<div id="result"></div>
{% endblock %}
```

`web/templates/partials/backtest_result.html`:
```html
{% if insufficient is defined %}
  <div class="banner warn">Only {{ insufficient }} trades — insufficient to validate. Widen lookback or loosen preset.</div>
{% elif result %}
  <div class="banner {{ 'ok' if verdict.robust else 'warn' }}">{{ '✓ Edge looks robust' if verdict.robust else '⚠ Edge not confirmed robust' }}</div>
  {% for r in verdict.reasons %}<div class="muted">· {{ r }}</div>{% endfor %}
  <div class="tiles">
    <div class="tile"><div class="label">Trades</div><div class="num">{{ result.n_trades }}</div></div>
    <div class="tile"><div class="label">Net P&L</div><div class="num g">₹{{ '%.0f'|format(result.net_pnl) }}</div></div>
    <div class="tile"><div class="label">Win rate</div><div class="num">{{ result.win_rate }}%</div></div>
    <div class="tile"><div class="label">Expectancy</div><div class="num">₹{{ result.expectancy }}</div></div>
  </div>
  <p class="muted">Walk-forward: {{ wf.pct_folds_profitable }}% of {{ wf.n_folds }} windows profitable ·
     MC drawdown p95 ₹{{ mc.p95 }} · bootstrap CI ₹{{ ci.lo }}…₹{{ ci.hi }}</p>
{% else %}
  <div class="muted">No result.</div>
{% endif %}
```

- [ ] **Step 5: Add `backtest` to server import list.**

- [ ] **Step 6: Run tests + commit**

Run: `pytest tests/web/test_backtest_web.py -v` → 2 passed. `pytest tests/ -q` → green.
```bash
git add web/routes/backtest.py web/templates/backtest.html web/templates/partials/backtest_result.html web/server.py tests/web/test_backtest_web.py
git commit -m "feat(web): backtest page with robustness verdict"
```

---

## Task 9: Options, Settings, Go-Live, BTST pages

Four thinner pages. Each: route + template + a TestClient test asserting the page renders
(200 + a known label) and, where it has an action, that the action returns the expected
partial. Reuse the patterns above.

**Files:**
- Create: `web/routes/options.py`, `web/routes/settings.py`, `web/routes/golive.py`, `web/routes/btst.py`
- Create: `web/templates/options.html`, `settings.html`, `golive.html`, `btst.html` (+ `partials/payoff.html`, `partials/btst_scan.html`)
- Modify: `web/server.py` (add all four)
- Test: `tests/web/test_pages_misc.py`

- [ ] **Step 1: Write `web/routes/settings.py`** (risk limits + bell + Dhan keys read/write via config_store)

```python
"""Settings page — read/write the same config_store keys the Streamlit Settings page uses."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core import config_store
from web.server import templates

router = APIRouter()
_val = lambda k, d="": config_store.get_setting(k, d)


@router.get("/settings", response_class=HTMLResponse)
def page(request: Request):
    keys = {k: _val(k) for k in ("DHAN_CLIENT_ID", "SIGNAL_SOURCE", "TRADE_MODE",
            "MAX_DAILY_LOSS", "MAX_RISK_PER_TRADE_PCT", "MAX_OPEN_POSITIONS",
            "ACCOUNT_CAPITAL", "BELL_ENABLED", "BELL_LEAD_MINUTES")}
    return templates.TemplateResponse("settings.html", {"request": request, "k": keys})


@router.post("/settings/save", response_class=HTMLResponse)
def save(request: Request, dhan_id: str = Form(""), dhan_token: str = Form(""),
         signal_source: str = Form("mock"), trade_mode: str = Form("PAPER"),
         max_daily_loss: str = Form("10000"), max_risk: str = Form("1.0"),
         max_pos: str = Form("2"), capital: str = Form("100000"),
         bell_enabled: str = Form("true"), bell_lead: str = Form("10")):
    updates = {"DHAN_CLIENT_ID": dhan_id, "SIGNAL_SOURCE": signal_source,
               "TRADE_MODE": trade_mode, "MAX_DAILY_LOSS": max_daily_loss,
               "MAX_RISK_PER_TRADE_PCT": max_risk, "MAX_OPEN_POSITIONS": max_pos,
               "ACCOUNT_CAPITAL": capital, "BELL_ENABLED": bell_enabled,
               "BELL_LEAD_MINUTES": bell_lead}
    if dhan_token:
        updates["DHAN_ACCESS_TOKEN"] = dhan_token
    config_store.save({k: v for k, v in updates.items() if v != ""})
    return HTMLResponse('<div class="banner ok">Settings saved.</div>')
```

`web/templates/settings.html`:
```html
{% extends "base.html" %}
{% block title %}Settings — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>Settings</h2>
<form hx-post="/settings/save" hx-target="#saved" hx-swap="innerHTML">
  <p>Dhan client id <input name="dhan_id" value="{{ k.DHAN_CLIENT_ID }}"></p>
  <p>Dhan access token <input name="dhan_token" type="password" placeholder="(unchanged if blank)"></p>
  <p>Signal source <select name="signal_source"><option {{ 'selected' if k.SIGNAL_SOURCE=='mock' else '' }}>mock</option><option {{ 'selected' if k.SIGNAL_SOURCE=='api' else '' }}>api</option></select></p>
  <p>Trade mode <select name="trade_mode"><option {{ 'selected' if k.TRADE_MODE=='PAPER' else '' }}>PAPER</option><option {{ 'selected' if k.TRADE_MODE=='LIVE' else '' }}>LIVE</option></select></p>
  <p>Max daily loss ₹ <input name="max_daily_loss" value="{{ k.MAX_DAILY_LOSS or '10000' }}"></p>
  <p>Risk %/trade <input name="max_risk" value="{{ k.MAX_RISK_PER_TRADE_PCT or '1.0' }}"></p>
  <p>Max open positions <input name="max_pos" value="{{ k.MAX_OPEN_POSITIONS or '2' }}"></p>
  <p>Account capital (paper) <input name="capital" value="{{ k.ACCOUNT_CAPITAL or '100000' }}"></p>
  <p>Bell enabled <select name="bell_enabled"><option>true</option><option>false</option></select>
     lead min <input name="bell_lead" value="{{ k.BELL_LEAD_MINUTES or '10' }}" style="width:60px"></p>
  <button type="submit">💾 Save settings</button>
</form>
<div id="saved"></div>
{% endblock %}
```

- [ ] **Step 2: Write `web/routes/golive.py`**

```python
"""Go-Live page — the 5 readiness gates from core.readiness."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core import readiness
from web.server import templates

router = APIRouter()


def _ctx(request):
    state = readiness.get_state()
    gates = [{"id": g, "label": l, "kind": k, "passed": bool(state.get(g))}
             for g, l, k in readiness.GATES]
    return {"request": request, "gates": gates, "passed": readiness.passed_count(),
            "all": readiness.all_passed(), "total": len(readiness.GATE_IDS)}


@router.get("/golive", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse("golive.html", _ctx(request))


@router.post("/golive/gate", response_class=HTMLResponse)
def toggle(request: Request, gate_id: str = Form(...), value: str = Form("true")):
    readiness.set_gate(gate_id, value == "true")
    return templates.TemplateResponse("golive.html", _ctx(request))
```

`web/templates/golive.html`:
```html
{% extends "base.html" %}
{% block title %}Go-Live — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>Go-Live readiness</h2>
<div class="banner {{ 'ok' if all else 'warn' }}">{{ passed }}/{{ total }} gates passed — LIVE {{ 'unlocked' if all else 'locked' }}</div>
{% for g in gates %}
  <div class="card">
    <b>{{ g.label }}</b> <span class="muted">({{ g.kind }})</span>
    <span class="{{ 'chip q' if g.passed else 'chip qlow' }}">{{ 'PASS' if g.passed else 'not yet' }}</span>
    <form hx-post="/golive/gate" hx-target="body" hx-swap="none" hx-on::after-request="location.reload()" style="display:inline">
      <input type="hidden" name="gate_id" value="{{ g.id }}">
      <input type="hidden" name="value" value="{{ 'false' if g.passed else 'true' }}">
      <button>{{ 'Uncheck' if g.passed else 'Mark done' }}</button>
    </form>
  </div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 3: Write `web/routes/options.py`** (chain + payoff)

```python
"""Options page — expiries/chain + payoff via services.options_chain/options_payoff."""
from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from core.models import Instrument
from services.options_chain import get_expiries, get_chain
from services.options_payoff import payoff_curve, metrics
from services import charting
from ui import themes
from web import deps, charts
from web.server import templates

router = APIRouter()


@router.get("/options", response_class=HTMLResponse)
def page(request: Request):
    syms = [i for i in deps.load_watchlist() if i.kind == "INDEX"]
    return templates.TemplateResponse("options.html", {"request": request, "syms": syms})


@router.post("/options/chain", response_class=HTMLResponse)
def chain(request: Request, symbol: str = Form(...), security_id: str = Form(...),
          exchange_segment: str = Form("IDX_I")):
    dhan = deps.get_dhan()
    instr = Instrument(symbol=symbol, exchange_segment=exchange_segment,
                       security_id=security_id, kind="INDEX")
    expiries = get_expiries(instr, dhan)
    rows = get_chain(instr, expiries[0], dhan) if expiries else []
    return templates.TemplateResponse("partials/payoff.html",
                                      {"request": request, "expiries": expiries, "rows": rows})
```

`web/templates/options.html`:
```html
{% extends "base.html" %}
{% block title %}Options — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>Options</h2>
{% if not syms %}<div class="banner warn">No resolved INDEX instrument in the watchlist.</div>{% endif %}
<form hx-post="/options/chain" hx-target="#chain" hx-swap="innerHTML">
  <select name="symbol" onchange="this.form.security_id.value=this.selectedOptions[0].dataset.sid">
    {% for s in syms %}<option data-sid="{{ s.security_id }}">{{ s.symbol }}</option>{% endfor %}
  </select>
  <input type="hidden" name="security_id" value="{{ syms[0].security_id if syms else '' }}">
  <button type="submit">Load chain</button>
</form>
<div id="chain"></div>
{% endblock %}
```

`web/templates/partials/payoff.html`:
```html
{% if not expiries %}<div class="banner warn">No expiries returned (Dhan options data unavailable).</div>
{% else %}
<p class="muted">Expiry {{ expiries[0] }} · {{ rows|length }} strikes</p>
<table><tr><th>Strike</th><th>CE ltp</th><th>PE ltp</th></tr>
{% for r in rows[:15] %}<tr><td>{{ r.strike }}</td><td>{{ r.ce.ltp }}</td><td>{{ r.pe.ltp }}</td></tr>{% endfor %}
</table>{% endif %}
```

- [ ] **Step 4: Write `web/routes/btst.py`**

```python
"""BTST page — near-close scan + overnight book (services.btst + market_clock)."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services import btst, market_clock
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from data.journal import open_btst_book
from web import deps
from web.server import templates

router = APIRouter()


@router.get("/btst", response_class=HTMLResponse)
def page(request: Request):
    now = datetime.now(timezone.utc)
    dhan = deps.get_dhan()

    def candles_fn(instr):
        return dhan.get_candles(instr, interval="day", lookback_days=400)

    def confluence_fn(df):
        return build_confluence(df, regime=None, style="positional", active_ids=list(range(1, 30)))

    candidates = btst.scan(deps.load_watchlist(), candles_fn=candles_fn,
                           confluence_fn=confluence_fn, active_ids=list(range(1, 30)))
    book = open_btst_book(deps.get_journal(), mode=deps.get_mode())
    return templates.TemplateResponse("btst.html", {
        "request": request, "near_close": market_clock.is_near_close(now),
        "candidates": candidates[:10], "book": book})
```

`web/templates/btst.html`:
```html
{% extends "base.html" %}
{% block title %}BTST — Dhan-Claude Trader{% endblock %}
{% block body %}
<h2>BTST — Buy Today, Sell Tomorrow</h2>
{% if not near_close %}<div class="banner warn">BTST scan runs 3:00–3:30 PM IST. Preview below.</div>{% endif %}
<h3>Candidates</h3>
{% for c in candidates %}
  <div class="card buy">
    <b>{{ c.instrument.symbol }}</b> · entry ₹{{ c.entry }} · target ₹{{ c.target }} · stop ₹{{ c.stop }}
    <div class="muted">{{ c.reasons|join(' · ') }}</div>
    <div class="banner halt">⚠ {{ c.gap_risk }}</div>
  </div>
{% else %}<div class="muted">No BTST candidates right now.</div>{% endfor %}
<h3>BTST book</h3>
{% for b in book %}<div class="card"><b>{{ b.symbol }}</b> qty {{ b.qty }} · exit {{ b.planned_exit_date }} · tgt {{ b.plan_target }}</div>
{% else %}<div class="muted">No open BTST positions.</div>{% endfor %}
{% endblock %}
```

- [ ] **Step 5: Tests** — `tests/web/test_pages_misc.py`:
```python
from fastapi.testclient import TestClient
from web.server import create_web_app
import web.deps as wdeps
from core import config_store


def _client(monkeypatch, fake_dhan, temp_journal, tmp_path):
    monkeypatch.setattr(wdeps, "get_dhan", lambda mode=None: fake_dhan)
    monkeypatch.setattr(wdeps, "get_journal", lambda: temp_journal)
    monkeypatch.setattr(wdeps, "load_watchlist", lambda path="watchlist.json": [])
    monkeypatch.setattr(wdeps, "get_mode", lambda: "PAPER")
    monkeypatch.setattr(config_store, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, tmp_path / "s.json"))
    monkeypatch.setattr(config_store.save, "__defaults__", (tmp_path / "s.json",))
    monkeypatch.setattr(config_store.load, "__defaults__", (tmp_path / "s.json",))
    from core import readiness
    for fn in ("get_state", "set_gate", "passed_count", "all_passed"):
        obj = getattr(readiness, fn)
        monkeypatch.setattr(obj, "__defaults__", (tmp_path / "s.json",))
    return TestClient(create_web_app())


def test_settings_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "Save settings" in c.get("/settings").text


def test_settings_save(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    r = c.post("/settings/save", data={"max_daily_loss": "5000"})
    assert "saved" in r.text.lower()
    assert config_store.load(tmp_path / "s.json")["MAX_DAILY_LOSS"] == "5000"


def test_golive_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "readiness" in c.get("/golive").text.lower()


def test_options_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert c.get("/options").status_code == 200


def test_btst_page(monkeypatch, fake_dhan, temp_journal, tmp_path):
    c = _client(monkeypatch, fake_dhan, temp_journal, tmp_path)
    assert "Buy Today" in c.get("/btst").text
```

- [ ] **Step 6: Add all four to `web/server.py`** import list:
```python
    from web.routes import dashboard, reports, screener, backtest, options, settings, golive, btst
    for mod in (dashboard, reports, screener, backtest, options, settings, golive, btst):
        app.include_router(mod.router)
```

- [ ] **Step 7: Run tests + commit**

Run: `pytest tests/web/ -q` → all green. `pytest tests/ -q` → 364 + web all green.
```bash
git add web/routes/ web/templates/ web/server.py tests/web/test_pages_misc.py
git commit -m "feat(web): options, settings, go-live, btst pages"
```

---

## Task 10: Launcher swap + run script + packaging + live verify

**Files:**
- Modify: `desktop/launcher.py`
- Modify: `desktop/build.spec`
- Create: `run_web.bat`

- [ ] **Step 1: Add `_start_web` to `desktop/launcher.py`** (next to `_start_streamlit`):

```python
def _start_web(port: int) -> None:
    """Serve the HTML web app headless (replaces the Streamlit server)."""
    try:
        import uvicorn
        from web.server import app
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception:                              # noqa: BLE001
        log.exception("web server thread crashed")
```

In `main()`, replace the streamlit thread start:
```python
        threading.Thread(target=_start_web, args=(port,), daemon=True,
                         name="web-server").start()
```
(Leave `_start_streamlit` in the file unused for now — a later cleanup removes Streamlit.)
The health URL is already `/health` on the web app, so `wait_for_health(base_url)` works
unchanged (it appends `/_stcore/health` — CHANGE that call: `wait_for_health(base_url,
health_path="/health")`, and add a `health_path="/_stcore/health"` param default to
`wait_for_health` so both work; update the one call site).

- [ ] **Step 2: Add the `health_path` param to `wait_for_health`** in `desktop/launcher.py`:
```python
def wait_for_health(base_url: str, *, timeout_s: int = HEALTH_TIMEOUT_S,
                    health_path: str = "/health",
                    get_fn=requests.get, sleep_fn=time.sleep, now_fn=time.monotonic) -> bool:
    deadline = now_fn() + timeout_s
    while now_fn() < deadline:
        try:
            r = get_fn(f"{base_url}{health_path}", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:                          # noqa: BLE001
            pass
        sleep_fn(0.25)
    return False
```
Run the existing launcher tests: `pytest tests/desktop/test_launcher.py -q` — update the
health tests if they asserted the `/_stcore/health` suffix (change the expected path to
the injected `health_path`). Keep them green.

- [ ] **Step 3: `run_web.bat`**
```batch
@echo off
cd /d "%~dp0"
echo Starting Dhan-Claude Trader (HTML)...
python -m uvicorn web.server:app --host 127.0.0.1 --port 8501
pause
```

- [ ] **Step 4: PyInstaller — ship templates + static.** In `desktop/build.spec` `datas`, add:
```python
    ("../web/templates", "web/templates"),
    ("../web/static", "web/static"),
    ("../web/__init__.py", "web"),
    ("../web/routes", "web/routes"),
    ("../web/server.py", "web"),
    ("../web/deps.py", "web"),
    ("../web/charts.py", "web"),
```
and add `"uvicorn"`, `"web.server"` to `hiddenimports`.

- [ ] **Step 5: Full suite + live manual verify**

Run: `pytest tests/ -q` → all green.
Run: `run_web.bat`, open `http://127.0.0.1:8501/` — the HTML dashboard renders with live
signal cards (same data the Streamlit app showed), auto-refreshing; Select → confirm →
Place a PAPER order → toast + it appears on `/reports`; HALT/Resume works; `/screener`
Run scan shows rows; `/backtest` Run shows a verdict; `/settings` saves; `/golive` toggles;
`/btst` lists candidates. Switch to a light theme via the `data-theme` attribute.

- [ ] **Step 6: Commit**
```bash
git add desktop/launcher.py desktop/build.spec run_web.bat tests/desktop/test_launcher.py
git commit -m "feat(web): launcher serves the HTML app; run_web.bat + PyInstaller datas"
```

---

## Task 11: Full-suite gate + branch finish

- [ ] **Step 1:** `pytest tests/ -q` — everything green (364 existing + all `tests/web/`).
- [ ] **Step 2:** `run_web.bat` boots clean; click through all 8 pages; place one PAPER order end-to-end; confirm it lands on Reports. Fix + re-run on any failure.
- [ ] **Step 3:** Merge `feature/html-frontend` → master, push. (Streamlit files remain for now; a follow-up slice removes `app.py`/`pages/` once the HTML app is trusted in daily use.)

---

## Self-Review Notes

- **Spec coverage:** §2 structure → Tasks 1–2, 3–9 (each page), 10 (launcher/packaging). §3 rendering model (htmx partials, 30s signal refresh, GET-never-places, charts via fig_json) → T3/T4/T5. §4 styling (terminal theme CSS) → T1. §5 auth/hosting (localhost, Cloudflare Access) → doc-level, no code needed. §6 error handling (error banner, insufficient message, halted refusal, htmx responseError) → T1/T3/T4. §7 launcher swap + run script + packaging → T10. §8 testing (TestClient per route, confirm-flow places once, GET never places, halted refuses) → T3/T4 + each page test. §9 rollout order → task order.
- **Safety preserved:** the two-step confirm is structural — `GET /dashboard/confirm` only renders; `POST /dashboard/place` is the sole placing route, re-derives + re-risk-checks server-side, and short-circuits when halted (tested: `test_get_confirm_does_not_place`, `test_place_refused_when_halted`). `trade_controller.confirm_and_place` unchanged.
- **No placeholders**; every route/template/test shown in full.
- **Type consistency:** `web.deps` helper names (`get_dhan`, `get_journal`, `get_mode`, `load_watchlist`, `get_equity`, `candles_for`, `style_for`, `get_risk_config`) used identically across all route modules and tests; `charts.fig_json` used by reports/options; `create_web_app()` consistent across tests.
- **Known follow-ups (out of scope, documented):** remove Streamlit `app.py`/`pages/` after adoption; theme switcher UI control (the CSS + `data-theme` support it; a picker widget is a small later add).
