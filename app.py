"""Dhan-Claude Trader — Streamlit dashboard (thin rendering layer).

All decisions live in services/* (risk_manager, trade_controller, signal_engine).
An order can ONLY fire via trade_controller.confirm_and_place, reachable solely from
the confirm dialog's second button. Run: `streamlit run app.py`.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
import os

from core.models import Instrument, TradeMode, SignalType, OrderType
from services import risk_manager, trade_controller, signal_engine
from services.dhan_client import DhanClient, DhanError
from services.strategies.engine import build_confluence
# register strategies
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services import indicators as ind
from data.journal import init_db, to_legs

load_dotenv()

st.set_page_config(page_title="Dhan-Claude Trader", layout="wide")

# ---------------------------------------------------------------- styling
st.markdown("""
<style>
  .stApp { background: #0b0f18; }
  section.main > div { padding-top: 0.5rem; }
  .card { background:#161d2e; border:1px solid #26314a; border-radius:14px;
          padding:14px 16px; margin-bottom:10px; }
  .buy { color:#34d399; font-weight:700; } .sell { color:#f87171; font-weight:700; }
  .hold { color:#fbbf24; font-weight:700; }
  .muted { color:#7c8499; font-size:0.85rem; }
  .chip { display:inline-block; background:#1e2740; border:1px solid #2d3a55;
          border-radius:8px; padding:2px 8px; margin:2px; font-size:0.75rem; }
  .pnl-pos { color:#34d399; font-weight:700; } .pnl-neg { color:#f87171; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- state
ss = st.session_state
ss.setdefault("mode", os.getenv("TRADE_MODE", "PAPER"))
ss.setdefault("signal_source", os.getenv("SIGNAL_SOURCE", "mock"))
ss.setdefault("pending", None)
ss.setdefault("last_refresh", 0.0)
ss.setdefault("signal_cache", {})


@st.cache_resource
def get_journal():
    return init_db("trades.db")


def get_client(mode: str) -> DhanClient:
    return DhanClient(client_id=os.getenv("DHAN_CLIENT_ID"),
                      access_token=os.getenv("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


def load_watchlist() -> list[Instrument]:
    data = json.loads(Path("watchlist.json").read_text())
    return [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                       security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                       kind=i.get("kind", "EQUITY"))
            for i in data["instruments"]]


def get_equity(mode: str, dhan: DhanClient) -> float:
    if mode == "LIVE":
        try:
            funds = dhan.get_fund_limits()
            return float(funds.get("availabelBalance", funds.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(os.getenv("ACCOUNT_CAPITAL", "100000"))


# ---------------------------------------------------------------- header
mode = ss["mode"]
cfg = risk_manager.load_risk_config()
journal = get_journal()
dhan = get_client(mode)

c1, c2, c3, c4 = st.columns([3, 1.4, 1.4, 1])
with c1:
    badge = "🟡 PAPER" if mode == "PAPER" else "🔴 LIVE"
    st.markdown(f"### Dhan-Claude Trader &nbsp; {badge}")
    st.caption("AI recommends · you confirm every trade")
with c2:
    ss["mode"] = st.selectbox("Trade mode", ["PAPER", "LIVE"],
                              index=0 if mode == "PAPER" else 1)
with c3:
    ss["signal_source"] = st.selectbox("Signal source", ["mock", "api"],
                                       index=0 if ss["signal_source"] == "mock" else 1)
with c4:
    if st.button("⟳ Refresh"):
        ss["signal_cache"] = {}
        ss["last_refresh"] = time.time()

# auto-refresh every 5 min
if time.time() - ss["last_refresh"] > 300:
    ss["signal_cache"] = {}
    ss["last_refresh"] = time.time()

# ---------------------------------------------------------------- risk panel
legs = to_legs(journal, mode=mode)
try:
    dpnl = risk_manager.day_pnl(TradeMode(mode), dhan_client=dhan, legs=legs,
                                ltp_fn=lambda s: None)
    open_count = risk_manager.open_position_count(TradeMode(mode), dhan_client=dhan,
                                                  legs=legs)
except DhanError as e:
    st.warning(f"Dhan read failed: {e}")
    dpnl, open_count = 0.0, 0

buffer = max(0.0, cfg.max_daily_loss + dpnl)
globally_blocked = dpnl <= -cfg.max_daily_loss or open_count >= cfg.max_open_positions

r1, r2, r3, r4 = st.columns(4)
pnl_cls = "pnl-pos" if dpnl >= 0 else "pnl-neg"
r1.markdown(f"**Today P&L**<br><span class='{pnl_cls}'>₹{dpnl:,.0f}</span>",
            unsafe_allow_html=True)
r2.markdown(f"**Loss buffer**<br>₹{buffer:,.0f} / ₹{cfg.max_daily_loss:,.0f}",
            unsafe_allow_html=True)
r3.markdown(f"**Open positions**<br>{open_count} / {cfg.max_open_positions}",
            unsafe_allow_html=True)
r4.markdown(("**Orders**<br>🔴 BLOCKED" if globally_blocked else "**Orders**<br>✅ allowed"),
            unsafe_allow_html=True)
if globally_blocked:
    st.error("New orders blocked: risk limit reached.")

st.divider()

# ---------------------------------------------------------------- signals
equity = get_equity(mode, dhan)
left, right = st.columns([2, 1])

with left:
    st.markdown("#### Live signals")
    for instr in load_watchlist():
        with st.container():
            try:
                style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
                candles = dhan.get_candles(instr, interval=15 if style == "intraday" else "day",
                                           lookback_days=10)
                if len(candles) < 30:
                    st.markdown(f"<div class='card'><b>{instr.symbol}</b> "
                                f"<span class='muted'>insufficient candle data</span></div>",
                                unsafe_allow_html=True)
                    continue
                snap = build_confluence(candles, regime=None, style=style,
                                        active_ids=list(range(1, 30)))
                last = float(candles["close"].iloc[-1])
                atr = float(ind.atr(candles).dropna().iloc[-1])
                cs = signal_engine.generate(
                    instr, snap, last_price=last, atr=atr, mode=ss["signal_source"],
                    cache=ss["signal_cache"])
            except DhanError as e:
                st.markdown(f"<div class='card'><b>{instr.symbol}</b> "
                            f"<span class='muted'>data error: {e}</span></div>",
                            unsafe_allow_html=True)
                continue

            sig = cs.consensus
            cls = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}[sig.value]
            snap_d = cs.indicator_snapshot
            chips = " ".join(
                f"<span class='chip'>{p.provider} {p.signal.value[:1]}{p.confidence}</span>"
                for p in cs.providers)
            st.markdown(
                f"<div class='card'><b>{instr.symbol}</b> · "
                f"<span class='muted'>{snap.regime.value}</span> &nbsp; "
                f"<span class='{cls}'>{sig.value} {cs.avg_confidence}%</span> "
                f"<span class='muted'>agree {cs.agreement_pct}%</span><br>"
                f"<span class='muted'>entry {snap_d.get('entry')} · SL {snap_d.get('stop_loss')} "
                f"· tgt {snap_d.get('target')}</span><br>{chips}</div>",
                unsafe_allow_html=True)

            if sig is not SignalType.HOLD and not globally_blocked:
                if st.button(f"Select {instr.symbol} →", key=f"sel_{instr.symbol}"):
                    ss["pending"] = trade_controller.prepare_order(
                        cs, instr, equity=equity, cfg=cfg, day_pnl_value=dpnl,
                        open_count=open_count)

with right:
    st.markdown("#### Open positions")
    try:
        positions = dhan.get_positions()
    except DhanError as e:
        positions = []
        st.caption(f"positions unavailable: {e}")
    if not positions:
        st.caption("No open positions.")
    for p in positions:
        net = int(p.get("netQty", 0) or 0)
        if net == 0:
            continue
        sym = p.get("tradingSymbol", p.get("securityId"))
        st.markdown(f"<div class='card'><b>{sym}</b> qty {net} · "
                    f"LTP {p.get('ltp', '-')}</div>", unsafe_allow_html=True)
        if st.button(f"Exit {sym} ✕", key=f"exit_{sym}"):
            instr = Instrument(symbol=str(sym), exchange_segment=p.get("exchangeSegment", ""),
                               security_id=str(p.get("securityId")), kind="EQUITY")
            res = dhan.exit_position(instr)
            st.toast(f"Exit: {res.status}")

# ---------------------------------------------------------------- confirm dialog
pending = ss.get("pending")
if pending is not None:
    @st.dialog("⚠ Confirm Order — step 2 of 2")
    def _confirm():
        req = pending.order_request
        rc = pending.risk_check
        st.write(f"**{req.instrument.symbol}** · {req.side.value} · qty {req.qty} "
                 f"· {req.order_type.value} @ {req.price}")
        st.write(f"SL {req.stop_loss} · target {req.target} · mode {mode}")
        if rc.allowed:
            st.success("Risk check ✅ passed")
        else:
            st.error("Blocked: " + "; ".join(rc.reasons))
        col_a, col_b = st.columns(2)
        if col_a.button("✓ Place Order", disabled=not rc.allowed, type="primary"):
            res = trade_controller.confirm_and_place(
                pending, dhan_client=dhan, journal_conn=journal,
                consensus=req.source_signal)
            st.toast(f"Order: {res.status}"
                     + (f" — {res.error_message}" if not res.ok else ""))
            ss["pending"] = None
            st.rerun()
        if col_b.button("Cancel"):
            ss["pending"] = None
            st.rerun()
    _confirm()
