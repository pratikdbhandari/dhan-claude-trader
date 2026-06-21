"""Options page — chain viewer, credit-spread builder, payoff diagram.
Defined-risk credit spreads only. Recommends; human still confirms order placement."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from core.models import Instrument, TradeMode, ConsensusSignal, SignalType
from services.dhan_client import DhanClient
from services import instruments
from services.options_chain import get_expiries, get_chain
from services.options_strategy import build_credit_spread
from services.options_payoff import payoff_curve

load_dotenv()
st.set_page_config(page_title="Options — Dhan-Claude Trader", layout="wide")
st.markdown("### ⚙️ Options — Credit Spread Builder")
st.caption("Defined-risk spreads. AI suggests direction; you confirm every order.")


@st.cache_resource
def _index():
    try:
        cache = Path("data/instrument_master.csv")
        text = cache.read_text(encoding="utf-8") if cache.exists() \
            else instruments.download_master()
        return instruments.build_index(text)
    except Exception:
        return {}


wl = json.loads(Path("watchlist.json").read_text())["instruments"]
idx_syms = [i["symbol"] for i in wl if i.get("kind") == "INDEX"] or ["NIFTY", "BANKNIFTY"]
symbol = st.selectbox("Underlying", idx_syms)
direction = st.radio("Bias", ["BUY (bull-put)", "SELL (bear-call)"], horizontal=True)
sell_delta = st.slider("Sell-leg delta", 0.15, 0.45, 0.30, 0.05)
lot_size = st.number_input("Lot size", min_value=1, value=50)

if st.button("Build spread"):
    dhan = DhanClient(client_id=os.getenv("DHAN_CLIENT_ID"),
                      access_token=os.getenv("DHAN_ACCESS_TOKEN"), mode=TradeMode.PAPER)
    instr = instruments.resolve(
        Instrument(symbol=symbol, exchange_segment="IDX_I", security_id=None,
                   kind="INDEX"), _index())
    if not instr.security_id:
        st.error(f"{symbol} security_id unresolved — cannot fetch chain.")
    else:
        expiries = get_expiries(instr, dhan)
        if not expiries:
            st.error("No expiries returned (need live Dhan creds / market data).")
        else:
            expiry = expiries[0]
            chain = get_chain(instr, expiry, dhan)
            if not chain:
                st.error("Empty option chain.")
            else:
                spot = chain[len(chain) // 2]["strike"]
                side = SignalType.BUY if direction.startswith("BUY") else SignalType.SELL
                cs = ConsensusSignal(instrument=instr, providers=[], consensus=side,
                                     avg_confidence=0, agreement_pct=0,
                                     indicator_snapshot={})
                plan = build_credit_spread(cs, chain, spot=spot, lot_size=int(lot_size),
                                           sell_delta=sell_delta)
                if plan is None:
                    st.error("Could not build spread (no greeks / strikes).")
                else:
                    st.markdown(f"#### {plan.name} · expiry {expiry}")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Net credit", f"₹{plan.credit:,.0f}")
                    c2.metric("Max profit", f"₹{plan.max_profit:,.0f}")
                    c3.metric("Max loss", f"₹{plan.max_loss:,.0f}")
                    st.write(f"Sell {plan.sell_strike} / Buy {plan.buy_strike} · "
                             f"breakevens {plan.breakevens}")
                    st.dataframe(pd.DataFrame(plan.legs), use_container_width=True)
                    xs, ys = payoff_curve(plan.legs, spot * 0.95, spot * 1.05)
                    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines", name="payoff"))
                    fig.add_hline(y=0, line=dict(color="#888", dash="dot"))
                    fig.update_layout(template="plotly_dark", height=320,
                                      title="Payoff at expiry",
                                      margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig, use_container_width=True)
                    st.info("Review legs + max loss before placing. Order placement "
                            "for multi-leg is manual in this build (leg-execution risk).")
