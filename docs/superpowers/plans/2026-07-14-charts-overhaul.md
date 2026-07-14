# Charts Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all charts theme-aware, polish presentation, and add equity-curve/drawdown, provider-accuracy, and themed payoff charts.

**Architecture:** `themes.chart_colors()` is the single source for the active theme's chart palette. `charting.py` gains `_theme_layout(colors)` and every builder takes `colors=None` (back-compat). New pure builders cover equity curve, provider accuracy, and payoff. Pages pass `chart_colors()` and disable the plotly modebar.

**Tech Stack:** plotly, pandas, pytest, Streamlit.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-charts-overhaul-design.md`](../specs/2026-07-14-charts-overhaul-design.md)

---

## Before You Start

- Branch `feature/charts-overhaul` (created). Repo-local git identity configured.
- Read `services/charting.py` (current builders), `ui/themes.py` (`THEMES`, `SIGNAL/GOLD/GREEN`, `apply()` reads `session_state["ui_theme"]`/`config_store.get_setting("UI_THEME","aura")`), `services/accounting.py` (`RealizedTrade`, `realized_trades`), `services/eod_report.py` (`build_report(...)["leaderboard"]` = `[{provider,calls,correct,accuracy}]`), `pages/3_Options.py` lines ~81–87 (inline payoff to replace).

---

## Task 1: themes.chart_colors()

**Files:**
- Modify: `ui/themes.py`
- Test: `tests/test_chart_colors.py`

- [ ] **Step 1: Write the failing test**

`tests/test_chart_colors.py`:
```python
from ui import themes


def test_chart_colors_has_all_keys():
    c = themes.chart_colors()
    for k in ("bg", "ink", "grid", "green", "signal", "gold", "accent"):
        assert k in c


def test_chart_colors_falls_back_to_aura_without_streamlit():
    c = themes.chart_colors()
    # aura is the default theme; bg/ink/accent come from its token set
    assert c["bg"] == themes.THEMES["aura"]["bg"]
    assert c["green"] == themes.GREEN and c["signal"] == themes.SIGNAL
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_chart_colors.py -v`
Expected: FAIL — `chart_colors` doesn't exist.

- [ ] **Step 3: Add `chart_colors()` to `ui/themes.py`** (after `THEME_NAMES`)

```python
def chart_colors() -> dict:
    """Active theme's chart palette. Never raises — falls back to aura outside a
    Streamlit run (so pure chart builders can call it anywhere)."""
    name = "aura"
    try:
        import streamlit as st
        name = st.session_state.get("ui_theme") or name
        if name == "aura":
            from core import config_store
            name = config_store.get_setting("UI_THEME", "aura")
    except Exception:                              # noqa: BLE001
        name = "aura"
    t = THEMES.get(name, THEMES["aura"])
    return {"bg": t["bg"], "ink": t["ink"], "grid": t["border"],
            "green": GREEN, "signal": SIGNAL, "gold": GOLD, "accent": t["accent"]}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_chart_colors.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ui/themes.py tests/test_chart_colors.py
git commit -m "feat(charts): themes.chart_colors() active-theme palette"
```

---

## Task 2: Theme-aware retrofit of existing builders

**Files:**
- Modify: `services/charting.py`
- Test: `tests/test_charting_theme.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_charting_theme.py`:
```python
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from services import charting


def _df(n=60):
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


_COLORS = {"bg": "#123456", "ink": "#eeeeee", "grid": "#333333",
           "green": "#00ff00", "signal": "#ff0000", "gold": "#ffcc00",
           "accent": "#0000ff"}


def test_price_chart_applies_theme_bg():
    fig = charting.price_chart(_df(), symbol="X", colors=_COLORS)
    assert isinstance(fig, go.Figure)
    assert fig.layout.paper_bgcolor == "#123456"
    assert fig.layout.plot_bgcolor == "#123456"


def test_price_chart_backcompat_no_colors():
    fig = charting.price_chart(_df(), symbol="X")
    assert isinstance(fig, go.Figure)          # still works with colors=None


def test_rsi_panel_applies_theme():
    fig = charting.rsi_panel(_df(), colors=_COLORS)
    assert fig.layout.paper_bgcolor == "#123456"


def test_macd_panel_applies_theme():
    fig = charting.macd_panel(_df(), colors=_COLORS)
    assert fig.layout.paper_bgcolor == "#123456"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_charting_theme.py -v`
Expected: FAIL — builders don't accept `colors`.

- [ ] **Step 3: Edit `services/charting.py`**

Add the default palette + layout helper at the top (after imports):
```python
_DEFAULT_COLORS = {"bg": "#0e1117", "ink": "#e6e9ef", "grid": "#232936",
                   "green": "#34d399", "signal": "#f87171", "gold": "#fbbf24",
                   "accent": "#60a5fa"}


def _theme_layout(colors: dict | None) -> dict:
    c = colors or _DEFAULT_COLORS
    return dict(paper_bgcolor=c["bg"], plot_bgcolor=c["bg"],
                font=dict(color=c["ink"]),
                xaxis=dict(gridcolor=c["grid"]), yaxis=dict(gridcolor=c["grid"]),
                margin=dict(l=8, r=8, t=8, b=8), showlegend=True,
                legend=dict(font=dict(size=10)))
```

Change `price_chart` signature to add `colors: dict | None = None`, use token colors for
candle + markers + volume, and replace its `update_layout` (drop `template`/`title`):
```python
def price_chart(df: pd.DataFrame, *, symbol: str = "", emas=(9, 21),
                bollinger: bool = True, markers: dict | None = None,
                colors: dict | None = None) -> go.Figure:
    c = colors or _DEFAULT_COLORS
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
                        vertical_spacing=0.03)
    x = list(range(len(df)))
    fig.add_trace(go.Candlestick(x=x, open=df["open"], high=df["high"],
                                 low=df["low"], close=df["close"], name="price",
                                 increasing_line_color=c["green"],
                                 decreasing_line_color=c["signal"]), row=1, col=1)
    for w in emas:
        if len(df) > w:
            fig.add_trace(go.Scatter(x=x, y=ind.ema(df["close"], w), mode="lines",
                                     name=f"EMA{w}", line=dict(width=1)), row=1, col=1)
    if bollinger and len(df) > 20:
        hi, mid, lo = ind.bollinger(df["close"])
        fig.add_trace(go.Scatter(x=x, y=hi, mode="lines", name="BB up",
                                 line=dict(width=1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=lo, mode="lines", name="BB low",
                                 line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=df["volume"], name="vol",
                         marker=dict(color=c["grid"])), row=2, col=1)
    markers = markers or {}
    last = len(df) - 1
    for key, color, sym in (("entry", c["green"], "triangle-up"),
                            ("stop_loss", c["signal"], "x"),
                            ("target", c["accent"], "circle")):
        val = markers.get(key)
        if val is not None:
            fig.add_trace(go.Scatter(x=[last], y=[val], mode="markers", name=key,
                                     marker=dict(color=color, size=11, symbol=sym)),
                          row=1, col=1)
    fig.update_layout(height=460, xaxis_rangeslider_visible=False,
                      **_theme_layout(colors))
    return fig
```

Change `rsi_panel` and `macd_panel` similarly — add `colors=None`, use `c` for line
colors, and `**_theme_layout(colors)` (drop `template`/`title`; keep height + the RSI
y-range):
```python
def rsi_panel(df: pd.DataFrame, colors: dict | None = None) -> go.Figure:
    c = colors or _DEFAULT_COLORS
    rsi = ind.rsi(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=rsi, mode="lines", name="RSI",
                             line=dict(color=c["accent"])))
    fig.add_hline(y=70, line=dict(color=c["signal"], dash="dot"))
    fig.add_hline(y=30, line=dict(color=c["green"], dash="dot"))
    lay = _theme_layout(colors)
    lay["yaxis"] = dict(range=[0, 100], gridcolor=c["grid"])
    fig.update_layout(height=180, **lay)
    return fig


def macd_panel(df: pd.DataFrame, colors: dict | None = None) -> go.Figure:
    c = colors or _DEFAULT_COLORS
    macd, signal, hist = ind.macd_lines(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=hist, name="hist", marker=dict(color=c["grid"])))
    fig.add_trace(go.Scatter(x=x, y=macd, mode="lines", name="MACD",
                             line=dict(color=c["accent"])))
    fig.add_trace(go.Scatter(x=x, y=signal, mode="lines", name="signal",
                             line=dict(color=c["gold"])))
    fig.update_layout(height=180, **_theme_layout(colors))
    return fig
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_charting_theme.py tests/test_charting.py -v`
Expected: new 4 pass; the existing `test_charting.py` still passes (adjust nothing there —
builders remain Figure-returning; if an existing test asserted `template=="plotly_dark"`
or a `title`, update that specific assertion to match the new theme-driven layout and note
it in the commit).

- [ ] **Step 5: Commit**

```bash
git add services/charting.py tests/test_charting_theme.py
git commit -m "feat(charts): theme-aware price/rsi/macd builders + config polish"
```

---

## Task 3: New builders (equity curve, provider accuracy, payoff)

**Files:**
- Modify: `services/charting.py`
- Test: `tests/test_charting_new.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_charting_new.py`:
```python
import plotly.graph_objects as go

from core.models import RealizedTrade
from services import charting


def _rt(net, closed):
    return RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
                         buy_price=100.0, sell_price=100.0 + net, gross_pnl=net,
                         charges=0.0, net_pnl=net, rr_predicted=None, rr_achieved=None,
                         opened_at="2026-07-01T09:00:00", closed_at=closed)


def test_equity_curve_returns_figure_and_cumulates():
    trades = [_rt(100, "2026-07-01T15:00:00"), _rt(-40, "2026-07-02T15:00:00"),
              _rt(60, "2026-07-03T15:00:00")]
    fig = charting.equity_curve(trades, colors=None)
    assert isinstance(fig, go.Figure)
    # first trace is the cumulative equity line: 100, 60, 120
    ys = list(fig.data[0].y)
    assert ys == [100, 60, 120]


def test_equity_curve_empty_returns_figure():
    fig = charting.equity_curve([], colors=None)
    assert isinstance(fig, go.Figure)


def test_provider_accuracy_bar_per_provider():
    rows = [{"provider": "claude", "calls": 10, "correct": 7, "accuracy": 70.0},
            {"provider": "groq", "calls": 8, "correct": 3, "accuracy": 37.5}]
    fig = charting.provider_accuracy(rows, colors=None)
    assert isinstance(fig, go.Figure)
    assert list(fig.data[0].x) == [70.0, 37.5] or list(fig.data[0].y) == [70.0, 37.5]


def test_provider_accuracy_empty_returns_figure():
    assert isinstance(charting.provider_accuracy([], colors=None), go.Figure)


def test_payoff_returns_figure_with_breakevens():
    xs = [90, 95, 100, 105, 110]
    ys = [-50, 0, 50, 0, -50]
    fig = charting.payoff(xs, ys, breakevens=[95, 105], colors=None)
    assert isinstance(fig, go.Figure)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_charting_new.py -v`
Expected: FAIL — new builders missing.

- [ ] **Step 3: Append to `services/charting.py`**

```python
def equity_curve(trades: list, colors: dict | None = None) -> go.Figure:
    """Cumulative net-P&L line + drawdown fill from closed RealizedTrades
    (sorted by closed_at). Empty -> annotated empty figure."""
    c = colors or _DEFAULT_COLORS
    fig = go.Figure()
    rows = sorted([t for t in trades], key=lambda t: t.closed_at)
    if not rows:
        fig.add_annotation(text="no closed trades", showarrow=False,
                           font=dict(color=c["ink"]))
        fig.update_layout(height=300, **_theme_layout(colors))
        return fig
    equity, run, peak, dd = [], 0.0, float("-inf"), []
    for t in rows:
        run = round(run + t.net_pnl, 2)
        equity.append(run)
        peak = max(peak, run)
        dd.append(round(run - peak, 2))
    x = list(range(len(equity)))
    fig.add_trace(go.Scatter(x=x, y=equity, mode="lines", name="equity",
                             line=dict(color=c["accent"], width=2)))
    fig.add_trace(go.Scatter(x=x, y=dd, mode="lines", name="drawdown",
                             fill="tozeroy", line=dict(color=c["signal"], width=1)))
    fig.update_layout(height=300, **_theme_layout(colors))
    return fig


def provider_accuracy(rows: list, colors: dict | None = None) -> go.Figure:
    """Horizontal accuracy bars per provider from the EOD leaderboard.
    Empty -> annotated empty figure."""
    c = colors or _DEFAULT_COLORS
    fig = go.Figure()
    if not rows:
        fig.add_annotation(text="no scored calls yet", showarrow=False,
                           font=dict(color=c["ink"]))
        fig.update_layout(height=220, **_theme_layout(colors))
        return fig
    names = [r["provider"] for r in rows]
    acc = [r["accuracy"] for r in rows]
    bar_colors = [c["green"] if a >= 50 else c["signal"] for a in acc]
    fig.add_trace(go.Bar(x=acc, y=names, orientation="h",
                         marker=dict(color=bar_colors)))
    lay = _theme_layout(colors)
    lay["xaxis"] = dict(range=[0, 100], gridcolor=c["grid"], title="accuracy %")
    fig.update_layout(height=220, **lay)
    return fig


def payoff(xs: list, ys: list, breakevens: list | None = None,
           colors: dict | None = None) -> go.Figure:
    """Options payoff area: green where profit, signal where loss, zero line +
    optional vertical breakeven markers."""
    c = colors or _DEFAULT_COLORS
    fig = go.Figure()
    pos = [y if y >= 0 else None for y in ys]
    neg = [y if y < 0 else None for y in ys]
    fig.add_trace(go.Scatter(x=xs, y=pos, mode="lines", name="profit",
                             fill="tozeroy", line=dict(color=c["green"])))
    fig.add_trace(go.Scatter(x=xs, y=neg, mode="lines", name="loss",
                             fill="tozeroy", line=dict(color=c["signal"])))
    fig.add_hline(y=0, line=dict(color=c["ink"], dash="dot"))
    for be in (breakevens or []):
        fig.add_vline(x=be, line=dict(color=c["gold"], dash="dot"))
    fig.update_layout(height=320, **_theme_layout(colors))
    return fig
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_charting_new.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/charting.py tests/test_charting_new.py
git commit -m "feat(charts): equity-curve/drawdown, provider-accuracy, themed payoff builders"
```

---

## Task 4: Wire dashboard, Reports, Options (manual verify)

**Files:**
- Modify: `app.py`, `pages/1_Reports.py`, `pages/3_Options.py`

Presentation-only; verified by running.

- [ ] **Step 1: Dashboard (`app.py`)** — before the signal loop, get colors once:
  `from ui import themes as _themes` is already imported as `themes`? It imports
  `from ui import themes`. Add `_cc = themes.chart_colors()` near the top of the signals
  section. Pass `colors=_cc` to the three chart calls and add the no-modebar config:
```python
st.plotly_chart(charting.price_chart(candles, symbol=instr.symbol, markers=markers,
                colors=_cc), use_container_width=True, key=f"px_{instr.symbol}",
                config={"displayModeBar": False})
cc1.plotly_chart(charting.rsi_panel(candles, colors=_cc), use_container_width=True,
                 key=f"rsi_{instr.symbol}", config={"displayModeBar": False})
cc2.plotly_chart(charting.macd_panel(candles, colors=_cc), use_container_width=True,
                 key=f"macd_{instr.symbol}", config={"displayModeBar": False})
```

- [ ] **Step 2: Reports (`pages/1_Reports.py`)** — add imports `from services import charting`
  and `from ui import themes`, then after the P&L section:
```python
st.markdown("#### Equity curve")
_cc = themes.chart_colors()
st.plotly_chart(charting.equity_curve(realized_trades(legs, mode=mode), colors=_cc),
                use_container_width=True, config={"displayModeBar": False})
st.markdown("#### Provider accuracy")
_rep = build_report(journal, mode=mode)
st.plotly_chart(charting.provider_accuracy(_rep.get("leaderboard", []), colors=_cc),
                use_container_width=True, config={"displayModeBar": False})
```
(`realized_trades`, `build_report` are already imported on that page — verify and add only
if missing.)

- [ ] **Step 3: Options (`pages/3_Options.py`)** — replace the inline payoff block
  (the `fig = go.Figure(go.Scatter(...))` through `st.plotly_chart(fig, ...)`) with:
```python
from services import charting
from ui import themes
xs, ys = payoff_curve(plan.legs, spot * 0.95, spot * 1.05)
st.plotly_chart(charting.payoff(xs, ys, breakevens=plan.breakevens,
                colors=themes.chart_colors()), use_container_width=True,
                config={"displayModeBar": False})
```
(Move the two imports to the top of the file with the others.)

- [ ] **Step 4: Manual verification**

Run `streamlit run app.py`:
- Dashboard: expand a signal chart — candles/RSI/MACD match the active theme; switch
  theme (aura ↔ terminal ↔ a light theme) and confirm charts recolor; no plotly modebar.
- Reports: equity curve + drawdown render (or "no closed trades"); provider-accuracy bars
  render (or "no scored calls yet").
- Options: build a spread → payoff shows green/red areas + breakeven lines, themed.

- [ ] **Step 5: Commit**

```bash
git add app.py pages/1_Reports.py pages/3_Options.py
git commit -m "feat(charts): wire theme-aware charts into dashboard, reports, options"
```

---

## Task 5: Full-suite gate

- [ ] **Step 1:** `pytest tests/ -q` — all green (new chart tests + every prior test).
- [ ] **Step 2:** `streamlit run app.py` boots clean; charts render on `terminal` + one
  light theme; no traceback. Fix + re-run if needed.

---

## Self-Review Notes

- **Spec coverage:** §3 chart_colors → T1. §4 _theme_layout + retrofit → T2. §5 new
  builders → T3. §6 wiring → T4. §7 edges → empty-data tests (T3), colors=None back-compat
  (T2/T3), defensive chart_colors (T1). §8 testing → T1–T3 unit; T4 manual.
- **Existing test risk:** `tests/test_charting.py` may assert `plotly_dark`/`title`; T2
  step 4 flags updating any such assertion to the new layout.
- **No placeholders**; all builder code shown in full.
- **Type consistency:** `colors` dict keys (`bg,ink,grid,green,signal,gold,accent`)
  identical across `chart_colors()`, `_DEFAULT_COLORS`, `_theme_layout`, and every
  builder + test; `equity_curve(trades,colors)`, `provider_accuracy(rows,colors)`,
  `payoff(xs,ys,breakevens,colors)` match their call sites in T4.
