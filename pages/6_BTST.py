"""BTST (Buy Today, Sell Tomorrow) — near-close candidate scan + overnight book.
Thin render; all logic in services/btst, services/market_clock, trade_controller."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.models import Instrument, TradeMode
from core import config_store
from services import btst, market_clock, risk_manager, trade_controller
from services.dhan_client import DhanClient, DhanError
from services.strategies.engine import build_confluence
import services.strategies.trend        # noqa: F401  register strategies
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout     # noqa: F401
import services.strategies.volume       # noqa: F401
import services.strategies.structure    # noqa: F401
from data.journal import init_db, log_order, open_btst_book
from services import instruments
from ui import themes

load_dotenv()
st.set_page_config(page_title="BTST — Dhan-Claude Trader", layout="wide")
themes.apply()

ss = st.session_state
ss.setdefault("mode", config_store.get_setting("TRADE_MODE", "PAPER"))
ss.setdefault("btst_pending", None)


@st.cache_resource
def _journal():
    return init_db("trades.db")


def _client(mode: str) -> DhanClient:
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


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


def _equity(mode: str, dhan: DhanClient) -> float:
    if mode == "LIVE":
        try:
            f = dhan.get_fund_limits()
            return float(f.get("availabelBalance", f.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


mode = ss["mode"]
cfg = risk_manager.load_risk_config({
    "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
    "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
    "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
})
journal = _journal()
dhan = _client(mode)
now = datetime.now(timezone.utc)

st.markdown(f"### BTST — Buy Today, Sell Tomorrow &nbsp; {'🟡 PAPER' if mode=='PAPER' else '🔴 LIVE'}")
st.caption("Scan near close · hold overnight · sell tomorrow · you confirm every trade")

# ---------------- candidates ----------------
st.markdown("#### Today's BTST candidates")
run_scan = market_clock.is_near_close(now)
if not run_scan:
    st.info("BTST scan runs 3:00–3:30 PM IST. You can dry-run a preview now.")
if run_scan or st.button("Scan now (preview)"):
    def candles_fn(instr):
        return dhan.get_candles(instr, interval="day", lookback_days=40)

    def confluence_fn(df):
        return build_confluence(df, regime=None, style="positional",
                                active_ids=list(range(1, 30)))
    try:
        candidates = btst.scan(_watchlist(), candles_fn=candles_fn,
                               confluence_fn=confluence_fn, active_ids=list(range(1, 30)))
    except DhanError as e:
        candidates = []
        st.warning(f"Scan failed: {e}")

    equity = _equity(mode, dhan)
    if not candidates:
        st.caption("No BTST candidates right now.")
    for c in candidates[:10]:
        with st.container():
            st.markdown(f"**{c.instrument.symbol}** · entry ₹{c.entry} · "
                        f"target ₹{c.target} · stop ₹{c.stop}")
            st.caption(" · ".join(c.reasons))
            st.error(f"⚠ {c.gap_risk}")
            if st.button(f"Select {c.instrument.symbol} →", key=f"btst_{c.instrument.symbol}"):
                ss["btst_pending"] = (c, trade_controller.prepare_btst_order(
                    c, equity=equity, cfg=cfg, day_pnl_value=0.0, open_count=0))

pending = ss.get("btst_pending")
if pending is not None:
    cand, po = pending

    @st.dialog("⚠ Confirm BTST Order — step 2 of 2")
    def _confirm():
        req = po.order_request
        st.write(f"**{req.instrument.symbol}** BUY {req.qty} @ ₹{req.price} (CNC delivery)")
        st.write(f"Plan: target ₹{cand.target} · stop ₹{cand.stop}")
        st.error(f"⚠ {cand.gap_risk}")
        if not po.risk_check.allowed:
            st.error("Blocked: " + "; ".join(po.risk_check.reasons))
        c1, c2 = st.columns(2)
        if c1.button("Place BTST Order", disabled=not po.risk_check.allowed):
            # journal_conn=None: confirm_and_place must NOT log here; we log once below
            # with the BTST plan columns so open_btst_book can find the position.
            res = trade_controller.confirm_and_place(po, dhan_client=dhan,
                                                     journal_conn=None)
            if res.ok:
                log_order(journal, req, res, strategy_tag="BTST",
                          planned_exit_date=str(market_clock.next_trading_day(now.date())),
                          plan_target=cand.target, plan_stop=cand.stop)
            st.toast(f"BTST: {res.status}")
            ss["btst_pending"] = None
            st.rerun()
        if c2.button("Cancel"):
            ss["btst_pending"] = None
            st.rerun()
    _confirm()

# ---------------- book ----------------
st.divider()
st.markdown("#### BTST Book — open overnight positions")
book = open_btst_book(journal, mode=mode)
if not book:
    st.caption("No open BTST positions.")
today = now.astimezone(market_clock.IST).date()
for b in book:
    due = b["planned_exit_date"] and str(today) >= b["planned_exit_date"]
    st.markdown(f"**{b['symbol']}** qty {b['qty']} · entry ₹{b['entry']} · "
                f"target ₹{b['plan_target']} · stop ₹{b['plan_stop']} · "
                f"exit {b['planned_exit_date']}")
    if due:
        st.warning("🔔 SELL reminder — planned exit day reached.")
        if st.button(f"Exit {b['symbol']} ✕", key=f"exit_{b['symbol']}"):
            instr = Instrument(symbol=b["symbol"],
                               exchange_segment=b["exchange_segment"],
                               security_id=str(b["security_id"]), kind="EQUITY")
            res = dhan.exit_position(instr)
            st.toast(f"Exit: {res.status}")
