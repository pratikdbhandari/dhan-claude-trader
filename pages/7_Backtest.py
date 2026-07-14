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
