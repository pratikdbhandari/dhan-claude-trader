# Charts Overhaul Design — Theme-Aware + Wider Coverage

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/charting.py`, `ui/themes.py`, `services/accounting.realized_trades`, `services/eod_report._leaderboard`/`build_report`, `services/options_payoff.payoff_curve`, `app.py`, `pages/1_Reports.py`, `pages/3_Options.py`.

---

## 1. Purpose

Make every chart in the app match the active theme, polish their presentation, and add
the high-value charts that are missing. Fixes the current jar where charts hardcode
`plotly_dark` + fixed hex and clash with the light themes and the new `terminal` theme.

**Principles:** chart builders stay pure (`df`/data in → `go.Figure` out, no Streamlit);
theme colors are passed in explicitly (testable, no hidden coupling); existing callers
keep working when no colors are passed (back-compat default).

**Out of scope:** switching charting libraries (stay on plotly), new indicators, live
streaming candles, chart interactivity beyond plotly defaults.

---

## 2. Modules

```
ui/themes.py            ADD chart_colors() -> dict: the ACTIVE theme's chart-relevant
                          tokens {bg, ink, grid, green, signal, gold, accent}. Reads the
                          persisted choice (session_state["ui_theme"] or
                          config_store.get_setting("UI_THEME", "aura")).

services/charting.py    ADD _theme_layout(colors) -> dict (plotly layout kwargs).
                        CHANGE price_chart/rsi_panel/macd_panel: add colors=None param,
                          apply _theme_layout, use token green/signal for candles+markers,
                          drop redundant title, tight margins. colors=None => current
                          look (back-compat).
                        ADD equity_curve(trades, colors=None) -> Figure
                            provider_accuracy(rows, colors=None) -> Figure
                            payoff(xs, ys, breakevens=None, colors=None) -> Figure

app.py                  Dashboard: pass charting theme colors into the 3 charts +
                          st.plotly_chart(..., config={"displayModeBar": False}).
pages/1_Reports.py      ADD equity-curve/drawdown chart (realized_trades) + provider-
                          accuracy bar (EOD leaderboard).
pages/3_Options.py      Replace the inline plotly payoff with charting.payoff(...).
```

No change to how any data is computed — charts read existing outputs.

---

## 3. Theme colors (`ui/themes.py`)

```python
def chart_colors() -> dict:
    """Active theme's chart palette. Safe outside Streamlit (falls back to aura)."""
```
Resolves the active theme name (try `st.session_state["ui_theme"]`; else
`config_store.get_setting("UI_THEME", "aura")`; on any error → `"aura"`), then returns:
`{"bg": t["bg"], "ink": t["ink"], "grid": t["border"], "green": GREEN,
"signal": SIGNAL, "gold": GOLD, "accent": t["accent"]}`. Import of streamlit/config_store
is done defensively so the function never raises (charts must render even if called in a
bare context).

## 4. `_theme_layout(colors)` (`services/charting.py`)

Returns plotly layout kwargs applied by every builder:
`paper_bgcolor=colors["bg"]`, `plot_bgcolor=colors["bg"]`,
`font=dict(color=colors["ink"])`, axis `gridcolor=colors["grid"]`,
`margin=dict(l=8, r=8, t=8, b=8)`, `legend` compact, no `template` (so it doesn't fight
the explicit colors). When `colors is None`, builders use a module default dict that
reproduces today's dark look (so untouched callers are visually unchanged).

## 5. New builders

- `equity_curve(trades, colors=None)` — `trades` = `list[RealizedTrade]` sorted by
  `closed_at`; cumulative sum of `net_pnl` → line (accent), plus a drawdown fill
  (running-max minus equity) as a shaded area below. Empty list → a Figure with a
  centered "no closed trades" annotation.
- `provider_accuracy(rows, colors=None)` — `rows` = EOD leaderboard
  `[{provider, calls, correct, accuracy}]`; horizontal bar of `accuracy` per provider,
  bar color green≥50 else signal. Empty → "no scored calls yet" annotation.
- `payoff(xs, ys, breakevens=None, colors=None)` — filled area (green where ys≥0, signal
  where <0), zero line, optional vertical breakeven markers. Replaces the Options inline
  chart.

## 6. Wiring

- **Dashboard** (`app.py`): compute `_cc = charting_colors()` once (via `themes.chart_colors()`),
  pass to the 3 chart calls, and add `config={"displayModeBar": False}` to each
  `st.plotly_chart`.
- **Reports** (`pages/1_Reports.py`): after the P&L section, add the equity curve
  (`charting.equity_curve(realized_trades(legs, mode), themes.chart_colors())`) and the
  provider-accuracy bar from the EOD report's leaderboard (`build_report(...)["leaderboard"]`).
- **Options** (`pages/3_Options.py`): replace the inline `go.Figure(...)` payoff with
  `charting.payoff(xs, ys, breakevens=..., colors=themes.chart_colors())`.

## 7. Error / edge handling

- `colors=None` anywhere → module default (today's look), never a crash.
- `chart_colors()` never raises (defensive imports, aura fallback).
- Empty realized trades / empty leaderboard → annotated empty Figure, not an exception.
- Unparseable timestamps in equity curve → those trades skipped.
- Options payoff with no breakevens → just the area + zero line.

## 8. Testing

- `chart_colors()`: returns all required keys; falls back to aura keys without Streamlit.
- `_theme_layout(colors)`: `paper_bgcolor`/`plot_bgcolor` == `colors["bg"]`; gridcolor set.
- `price_chart`/`rsi_panel`/`macd_panel`: return `go.Figure`; with a colors dict, the
  figure's `layout.paper_bgcolor == colors["bg"]`; with `colors=None`, still returns a
  Figure (back-compat).
- `equity_curve`: cumulative + drawdown values correct for a small trade list; empty list
  returns a Figure (no raise).
- `provider_accuracy`: bar per provider; empty rows return a Figure.
- `payoff`: returns a Figure; breakeven markers count matches input.
- Pages verified by running (charts theme-match across `terminal`/`aura`/a light theme).
