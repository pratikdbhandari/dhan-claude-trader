# Backtest Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add walk-forward, Monte Carlo drawdown, and bootstrap-CI validation over the existing backtest, plus a Backtest page that renders a plain-English robustness verdict.

**Architecture:** New pure, seeded `services/backtest_robust.py` operates on `simulate`'s `BacktestResult`/trades and on `df` slices. Two new themed chart helpers. A thin `pages/7_Backtest.py` wires it up.

**Tech Stack:** Python stdlib (`random`, `statistics`), pandas, plotly, pytest, Streamlit.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-backtest-robustness-design.md`](../specs/2026-07-14-backtest-robustness-design.md)

---

## Before You Start

- Branch `feature/backtest-robustness` (created). Repo-local git identity configured.
- Read `services/backtest.py`: `simulate(df, *, active_ids, style, segment, atr_sl, atr_tgt, time_cap, warmup, qty, trail_atr) -> BacktestResult`; `_result(trades)`; `BacktestResult` fields (`trades, n_trades, wins, win_rate, gross_pnl, net_pnl, profit_factor, expectancy, max_drawdown, calibration`); `BacktestTrade.net_pnl`. Read `services/charting.py` (`_DEFAULT_COLORS`, `_theme_layout`).

---

## Task 1: Monte Carlo drawdown + bootstrap CI

**Files:**
- Create: `services/backtest_robust.py`
- Test: `tests/test_backtest_robust.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_backtest_robust.py`:
```python
from core.models import BacktestResult, BacktestTrade
from services.backtest_robust import monte_carlo_drawdown, bootstrap_ci


def _trade(net):
    return BacktestTrade(symbol="X", side="BUY", entry_idx=0, exit_idx=1,
                         entry_price=100.0, exit_price=100.0 + net, gross_pnl=net,
                         charges=0.0, net_pnl=net, exit_reason="TARGET",
                         regime="TRENDING", net_score=0.4)


def _result(nets):
    trades = [_trade(n) for n in nets]
    return BacktestResult(trades=trades, n_trades=len(trades), wins=0, win_rate=0.0,
                          gross_pnl=0.0, net_pnl=sum(nets), profit_factor=0.0,
                          expectancy=0.0, max_drawdown=0.0, calibration=[])


# 10 trades: nine +10 and one -50 -> single 50 drop, so max drawdown is 50 in ANY order.
_NETS = [10, 10, 10, 10, 10, 10, 10, 10, 10, -50]


def test_monte_carlo_drawdown_reproducible_and_correct():
    r = _result(_NETS)
    a = monte_carlo_drawdown(r, n=500, seed=0)
    b = monte_carlo_drawdown(r, n=500, seed=0)
    assert a == b                       # seeded -> reproducible
    assert a["insufficient"] is False
    # only one negative trade of -50 -> drawdown is always exactly 50
    assert a["worst"] == 50.0 and a["p95"] == 50.0 and a["mean"] == 50.0


def test_monte_carlo_insufficient_under_10_trades():
    r = _result([10, -5, 10])
    out = monte_carlo_drawdown(r, n=100, seed=0)
    assert out["insufficient"] is True


def test_bootstrap_ci_reproducible_and_bounded():
    r = _result(_NETS)                  # mean net = (90-50)/10 = 4.0
    a = bootstrap_ci(r, n=500, seed=0)
    b = bootstrap_ci(r, n=500, seed=0)
    assert a == b
    assert a["insufficient"] is False
    assert a["lo"] <= a["mean"] <= a["hi"]
    assert -6 <= a["mean"] <= 14        # centered near the true 4.0


def test_bootstrap_insufficient_under_10_trades():
    out = bootstrap_ci(_result([10, -5]), n=100, seed=0)
    assert out["insufficient"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_backtest_robust.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `services/backtest_robust.py`**

```python
"""Backtest robustness checks — pure, seeded (deterministic) validation over an
existing BacktestResult / candle frame. Reduces curve-fit risk; does not remove it."""
from __future__ import annotations
import random
import statistics

MIN_TRADES = 10


def _max_drawdown(nets: list[float]) -> float:
    cum, peak, mdd = 0.0, 0.0, 0.0
    for x in nets:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return round(mdd, 2)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def monte_carlo_drawdown(result, *, n: int = 1000, seed: int = 0) -> dict:
    """Shuffle trade order n times; distribution of max drawdown."""
    nets = [t.net_pnl for t in result.trades]
    if len(nets) < MIN_TRADES:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "worst": 0.0, "insufficient": True}
    rng = random.Random(seed)
    dds = []
    for _ in range(n):
        order = nets[:]
        rng.shuffle(order)
        dds.append(_max_drawdown(order))
    dds.sort()
    return {"mean": round(statistics.mean(dds), 2), "p50": _pct(dds, 0.50),
            "p95": _pct(dds, 0.95), "worst": max(dds), "insufficient": False}


def bootstrap_ci(result, *, n: int = 1000, seed: int = 0) -> dict:
    """Resample net_pnl with replacement; 95% CI on expectancy (mean net_pnl)."""
    nets = [t.net_pnl for t in result.trades]
    if len(nets) < MIN_TRADES:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "insufficient": True}
    rng = random.Random(seed)
    k = len(nets)
    means = []
    for _ in range(n):
        sample = [nets[rng.randrange(k)] for _ in range(k)]
        means.append(statistics.mean(sample))
    means.sort()
    return {"mean": round(statistics.mean(means), 2),
            "lo": round(_pct(means, 0.025), 2), "hi": round(_pct(means, 0.975), 2),
            "insufficient": False}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_backtest_robust.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add services/backtest_robust.py tests/test_backtest_robust.py
git commit -m "feat(backtest): Monte Carlo drawdown + bootstrap CI (pure, seeded)"
```

---

## Task 2: Walk-forward + robustness verdict

**Files:**
- Modify: `services/backtest_robust.py`
- Test: `tests/test_backtest_walkforward.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_backtest_walkforward.py`:
```python
import numpy as np
import pandas as pd

from services.backtest_robust import walk_forward, robustness_verdict


def _trending_df(n=1400):
    rng = np.random.default_rng(1)
    close = 100 + np.linspace(0, 120, n) + rng.normal(0, 1.0, n)
    high = close + 1.0
    low = close - 1.0
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


_SIM_KW = {"active_ids": list(range(1, 30)), "style": "intraday",
           "segment": "equity_intraday", "warmup": 200}


def test_walk_forward_returns_folds_and_aggregate():
    wf = walk_forward(_trending_df(), n_splits=3, sim_kwargs=_SIM_KW)
    assert wf["n_folds"] >= 1
    assert 0 <= wf["pct_folds_profitable"] <= 100
    for f in wf["folds"]:
        for k in ("net_pnl", "win_rate", "expectancy", "profit_factor",
                  "max_drawdown", "n_trades"):
            assert k in f


def test_walk_forward_insufficient_on_short_df():
    wf = walk_forward(_trending_df(n=210), n_splits=4, min_test=200,
                      sim_kwargs=_SIM_KW)
    assert wf["insufficient"] is True


def test_robustness_verdict_robust_when_all_pass():
    wf = {"pct_folds_profitable": 75.0, "insufficient": False}
    mc = {"p95": 1200.0, "insufficient": False}
    ci = {"lo": 15.0, "hi": 60.0, "insufficient": False}
    v = robustness_verdict(wf, mc, ci)
    assert v["robust"] is True
    assert v["reasons"]


def test_robustness_verdict_not_robust_when_ci_includes_zero():
    wf = {"pct_folds_profitable": 75.0, "insufficient": False}
    mc = {"p95": 1200.0, "insufficient": False}
    ci = {"lo": -5.0, "hi": 60.0, "insufficient": False}
    assert robustness_verdict(wf, mc, ci)["robust"] is False


def test_robustness_verdict_not_robust_when_insufficient():
    wf = {"pct_folds_profitable": 0.0, "insufficient": True}
    mc = {"p95": 0.0, "insufficient": True}
    ci = {"lo": 0.0, "hi": 0.0, "insufficient": True}
    assert robustness_verdict(wf, mc, ci)["robust"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_backtest_walkforward.py -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Append to `services/backtest_robust.py`**

```python
def walk_forward(df, *, n_splits: int = 4, min_test: int = 50,
                 sim_kwargs: dict) -> dict:
    """Evaluate simulate() over n_splits contiguous out-of-sample windows.
    Each window includes the shared warmup lead-in the engine needs. A genuine
    edge stays profitable across most windows; a curve-fit one won't."""
    from services.backtest import simulate
    warmup = int(sim_kwargs.get("warmup", 200))
    n = len(df)
    usable = n - warmup
    folds = []
    if usable > 0 and n_splits > 0:
        seg = usable // n_splits
        for i in range(n_splits):
            start = warmup + i * seg
            end = n if i == n_splits - 1 else warmup + (i + 1) * seg
            window = df.iloc[max(0, start - warmup):end]
            if end - start < min_test:
                continue
            res = simulate(window, **sim_kwargs)
            folds.append({"net_pnl": res.net_pnl, "win_rate": res.win_rate,
                          "expectancy": res.expectancy,
                          "profit_factor": res.profit_factor,
                          "max_drawdown": res.max_drawdown, "n_trades": res.n_trades})
    if len(folds) < 2:
        return {"folds": folds, "n_folds": len(folds), "mean_expectancy": 0.0,
                "pct_folds_profitable": 0.0, "insufficient": True}
    prof = sum(1 for f in folds if f["net_pnl"] > 0)
    mean_exp = round(sum(f["expectancy"] for f in folds) / len(folds), 2)
    return {"folds": folds, "n_folds": len(folds), "mean_expectancy": mean_exp,
            "pct_folds_profitable": round(100 * prof / len(folds), 1),
            "insufficient": False}


def robustness_verdict(wf: dict, mc: dict, ci: dict) -> dict:
    """Plain-English combine. Robust only when the edge survives all three checks.
    Honest: this reduces curve-fit risk, it does not guarantee future profit."""
    reasons = []
    ok = True
    if wf.get("insufficient") or mc.get("insufficient") or ci.get("insufficient"):
        return {"robust": False,
                "reasons": ["Insufficient trades/windows to validate — widen the "
                            "lookback or loosen the preset."]}
    if wf["pct_folds_profitable"] >= 60:
        reasons.append(f"{wf['pct_folds_profitable']}% of walk-forward windows profitable")
    else:
        ok = False
        reasons.append(f"only {wf['pct_folds_profitable']}% of windows profitable (<60%)")
    if ci["lo"] > 0:
        reasons.append(f"expectancy CI [{ci['lo']}, {ci['hi']}] excludes zero")
    else:
        ok = False
        reasons.append(f"expectancy CI [{ci['lo']}, {ci['hi']}] includes zero (edge may be noise)")
    reasons.append(f"p95 Monte-Carlo drawdown ₹{mc['p95']}")
    return {"robust": ok, "reasons": reasons}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_backtest_walkforward.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add services/backtest_robust.py tests/test_backtest_walkforward.py
git commit -m "feat(backtest): walk-forward evaluation + robustness verdict"
```

---

## Task 3: Chart helpers (fold bars + histogram)

**Files:**
- Modify: `services/charting.py`
- Test: `tests/test_charting_robust.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_charting_robust.py`:
```python
import plotly.graph_objects as go

from services import charting


def test_fold_bars_returns_figure():
    folds = [{"expectancy": 12.0}, {"expectancy": -3.0}, {"expectancy": 8.0}]
    fig = charting.fold_bars(folds, colors=None)
    assert isinstance(fig, go.Figure)


def test_fold_bars_empty_safe():
    assert isinstance(charting.fold_bars([], colors=None), go.Figure)


def test_histogram_returns_figure():
    fig = charting.histogram([1.0, 2.0, 2.0, 3.0, 5.0], colors=None, title="dd")
    assert isinstance(fig, go.Figure)


def test_histogram_empty_safe():
    assert isinstance(charting.histogram([], colors=None), go.Figure)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_charting_robust.py -v`
Expected: FAIL — helpers missing.

- [ ] **Step 3: Append to `services/charting.py`**

```python
def fold_bars(folds: list, colors: dict | None = None) -> go.Figure:
    """Walk-forward per-fold expectancy bars (green>=0 / signal<0)."""
    c = colors or _DEFAULT_COLORS
    fig = go.Figure()
    if not folds:
        fig.add_annotation(text="no folds", showarrow=False, font=dict(color=c["ink"]))
        fig.update_layout(height=220, **_theme_layout(colors))
        return fig
    exps = [f["expectancy"] for f in folds]
    labels = [f"fold {i+1}" for i in range(len(folds))]
    bar_colors = [c["green"] if e >= 0 else c["signal"] for e in exps]
    fig.add_trace(go.Bar(x=labels, y=exps, marker=dict(color=bar_colors)))
    fig.update_layout(height=220, **_theme_layout(colors))
    return fig


def histogram(values: list, colors: dict | None = None, title: str = "") -> go.Figure:
    """Generic themed histogram (e.g. Monte-Carlo drawdown distribution)."""
    c = colors or _DEFAULT_COLORS
    fig = go.Figure()
    if not values:
        fig.add_annotation(text="no data", showarrow=False, font=dict(color=c["ink"]))
        fig.update_layout(height=220, **_theme_layout(colors))
        return fig
    fig.add_trace(go.Histogram(x=values, marker=dict(color=c["accent"]), name=title))
    fig.update_layout(height=220, **_theme_layout(colors))
    return fig
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_charting_robust.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add services/charting.py tests/test_charting_robust.py
git commit -m "feat(charts): fold-bars + histogram helpers for backtest robustness"
```

---

## Task 4: Backtest page (manual verify)

**Files:**
- Create: `pages/7_Backtest.py`

Thin render; verified by running. Mirror the wiring patterns in `pages/6_BTST.py`
(imports, `_client`, `_index`, `_watchlist`, `themes.chart_colors()`).

- [ ] **Step 1: Write `pages/7_Backtest.py`**

```python
"""Backtest & robustness — run simulate, then walk-forward / Monte-Carlo / bootstrap
validation with a plain verdict. Thin render; logic in services/backtest[_robust]."""
from __future__ import annotations
import json
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.models import Instrument, TradeMode
from core import config_store
from services import backtest, backtest_robust, charting, instruments
from services.dhan_client import DhanClient, DhanError
from ui import themes

load_dotenv()
st.set_page_config(page_title="Backtest — Dhan-Claude Trader", layout="wide")
themes.apply()

st.markdown("### Backtest & robustness")
st.caption("Validate an edge before trusting capital. Reduces curve-fit risk — never zero.")


def _client() -> DhanClient:
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(config_store.get_setting("TRADE_MODE", "PAPER")))


@st.cache_resource
def _index():
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
                else instruments.download_master())
        return instruments.build_index(text)
    except Exception:                              # noqa: BLE001
        return {}


def _watchlist():
    data = json.loads(Path("watchlist.json").read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY")) for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, _index())


wl = _watchlist()
syms = [i.symbol for i in wl] or ["NIFTY"]
c1, c2, c3 = st.columns(3)
sym = c1.selectbox("Instrument", syms)
style = c2.selectbox("Style", ["intraday", "positional"])
lookback = c3.slider("Lookback (days)", 30, 365, 180)
instr = next((i for i in wl if i.symbol == sym), wl[0] if wl else None)

if st.button("Run backtest") and instr is not None:
    dhan = _client()
    try:
        candles = dhan.get_candles(instr, interval=15 if style == "intraday" else "day",
                                   lookback_days=lookback)
    except DhanError as e:
        st.error(f"Data fetch failed: {e}")
        st.stop()

    seg = "equity_intraday" if style == "intraday" else "equity_delivery"
    sim_kw = {"active_ids": list(range(1, 30)), "style": style, "segment": seg,
              "warmup": 200}
    result = backtest.simulate(candles, **sim_kw)

    if result.n_trades < 10:
        st.warning(f"Only {result.n_trades} trades — insufficient to validate. "
                   "Widen the lookback or loosen the preset.")
        st.stop()

    wf = backtest_robust.walk_forward(candles, n_splits=4, sim_kwargs=sim_kw)
    mc = backtest_robust.monte_carlo_drawdown(result)
    ci = backtest_robust.bootstrap_ci(result)
    verdict = backtest_robust.robustness_verdict(wf, mc, ci)
    cc = themes.chart_colors()

    if verdict["robust"]:
        st.success("✓ Edge looks robust")
    else:
        st.warning("⚠ Edge not confirmed robust")
    for r in verdict["reasons"]:
        st.caption("· " + r)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trades", result.n_trades)
    m2.metric("Net P&L", f"₹{result.net_pnl:,.0f}")
    m3.metric("Win rate", f"{result.win_rate}%")
    m4.metric("Expectancy", f"₹{result.expectancy}")

    st.markdown("#### Walk-forward (expectancy per window)")
    st.plotly_chart(charting.fold_bars(wf["folds"], colors=cc),
                    use_container_width=True, config={"displayModeBar": False})
    st.caption(f"{wf['pct_folds_profitable']}% of {wf['n_folds']} windows profitable")

    st.markdown("#### Monte-Carlo drawdown distribution")
    d1, d2, d3 = st.columns(3)
    d1.metric("Median DD", f"₹{mc['p50']}")
    d2.metric("p95 DD", f"₹{mc['p95']}")
    d3.metric("Worst DD", f"₹{mc['worst']}")

    st.markdown("#### Bootstrap expectancy CI (95%)")
    st.write(f"₹{ci['lo']} … ₹{ci['hi']}  (mean ₹{ci['mean']})")
```

- [ ] **Step 2: Manual verification**

Run `streamlit run app.py`, open the Backtest page. Pick an instrument, run:
- With enough data: verdict banner + reasons; metrics; walk-forward fold bars (themed);
  MC drawdown metrics; bootstrap CI range. Switch theme → charts recolor.
- With a tiny lookback / few trades: the "insufficient to validate" warning, no panels.
- Data-fetch failure surfaces an error, no crash.

- [ ] **Step 3: Commit**

```bash
git add pages/7_Backtest.py
git commit -m "feat(backtest): Backtest page — simulate + robustness verdict + charts"
```

---

## Task 5: Full-suite gate

- [ ] **Step 1:** `pytest tests/ -q` — all green (13 new tests + every prior test).
- [ ] **Step 2:** `streamlit run app.py` boots; Backtest page renders on `terminal` + a light theme; no traceback. Fix + re-run if needed.

---

## Self-Review Notes

- **Spec coverage:** §2 module → T1 (MC + bootstrap) + T2 (walk_forward + verdict). §3 page → T4. §4 chart helpers → T3. §5 edges → `<10` trades insufficient (T1 tests + page guard), `<2` folds insufficient (T2), seeded reproducibility (T1 tests), DhanError (T4). §6 testing → T1–T3 unit; T4 manual.
- **No placeholders**; full code in every step.
- **Type consistency:** `monte_carlo_drawdown(result,*,n,seed)`, `bootstrap_ci(result,*,n,seed)`, `walk_forward(df,*,n_splits,min_test,sim_kwargs)`, `robustness_verdict(wf,mc,ci)` identical across module, tests, and page; dict keys (`insufficient`, `p95`, `lo`/`hi`, `pct_folds_profitable`, `folds`) consistent; `charting.fold_bars(folds,colors)` / `histogram(values,colors,title)` match page calls; `simulate(...)` kwargs match the real signature.
- **Honesty:** verdict + page copy state this reduces, not eliminates, curve-fit risk (matches the project's existing caveat).
