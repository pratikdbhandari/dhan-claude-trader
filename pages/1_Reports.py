"""Reports page — accounting views + journal stats + EOD report generation.
Thin rendering; logic in services/accounting, data/journal, services/eod_report."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from data.journal import init_db, to_legs, stats
from services.accounting import realized_trades, portfolio, pnl_statement
from services.eod_report import build_report, write_report

load_dotenv()
st.set_page_config(page_title="Reports — Dhan-Claude Trader", layout="wide")
from ui import themes as _themes
_themes.apply()

st.markdown("### 📊 Reports & Accounting")


@st.cache_resource
def get_journal():
    return init_db("trades.db")


journal = get_journal()
mode = st.selectbox("Book", ["PAPER", "LIVE"], index=0)
legs = to_legs(journal, mode=mode)
ltp_fn = (lambda s: None)   # unrealized shown as n/a here; live LTP wired from main app

# ---- P&L account statement
stmt = pnl_statement(legs, mode=mode, period="all", period_key=None, ltp_fn=ltp_fn)
c1, c2, c3 = st.columns(3)
c1.metric("Net realized P&L", f"₹{stmt.net_realized:,.2f}")
c2.metric("Unrealized", f"₹{stmt.unrealized:,.2f}")
c3.metric("Total P&L", f"₹{stmt.total_pnl:,.2f}")

st.markdown("#### P&L account")
st.table(pd.DataFrame([{
    "Gross realized": stmt.gross_realized, "Brokerage": -stmt.brokerage,
    "STT": -stmt.stt, "Exchange+SEBI+stamp": -stmt.exchange_sebi_stamp,
    "GST": -stmt.gst, "Net realized": stmt.net_realized,
    "Unrealized": stmt.unrealized, "Total": stmt.total_pnl,
}]).T.rename(columns={0: "₹"}))

# ---- Portfolio holdings
st.markdown("#### Portfolio holdings")
holds = portfolio(legs, mode=mode, ltp_fn=ltp_fn)
if holds:
    st.dataframe(pd.DataFrame([h.__dict__ for h in holds]), use_container_width=True)
else:
    st.caption("No open holdings.")

# ---- Realized trades
st.markdown("#### Realized trades")
realized = realized_trades(legs, mode=mode)
if realized:
    st.dataframe(pd.DataFrame([r.__dict__ for r in realized]), use_container_width=True)
else:
    st.caption("No closed trades.")

# ---- Journal stats
s = stats(journal, mode)
st.markdown("#### Journal stats")
st.write(f"Trades {s['trades']} · Wins {s['wins']} · Win rate {s['win_rate']}% · "
         f"Avg R:R predicted {s['avg_rr_predicted']} vs achieved {s['avg_rr_achieved']}")

# ---- EOD report
st.divider()
if st.button("📄 Generate EOD Report"):
    rep = build_report(journal, mode=mode, ltp_fn=ltp_fn)
    md_path, csv_path = write_report(rep)
    st.success(f"Saved: {md_path} · {csv_path}")
    st.markdown("##### Provider leaderboard")
    if rep["leaderboard"]:
        st.dataframe(pd.DataFrame(rep["leaderboard"]), use_container_width=True)
    else:
        st.caption("No scored provider calls yet.")
    st.markdown("##### Summary")
    st.json(rep["summary"])
