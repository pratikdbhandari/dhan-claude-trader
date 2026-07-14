"""Reports page — accounting views + journal stats + EOD report generation.
Thin rendering; logic in services/accounting, data/journal, services/eod_report."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from data.journal import init_db, to_legs, stats
from services.accounting import realized_trades, portfolio, pnl_statement
from services.eod_report import build_report, write_report
from services import behavior, charting, audit, cost
from ui import themes

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

# ---- Equity curve + provider accuracy
_cc = themes.chart_colors()
st.markdown("#### Equity curve")
st.plotly_chart(charting.equity_curve(realized_trades(legs, mode=mode), colors=_cc),
                use_container_width=True, config={"displayModeBar": False})
st.markdown("#### Provider accuracy")
_rep = build_report(journal, mode=mode)
st.plotly_chart(charting.provider_accuracy(_rep.get("leaderboard", []), colors=_cc),
                use_container_width=True, config={"displayModeBar": False})

# ---- AI cost
st.markdown("#### 💸 AI cost")
_runs = cost.read_runs()
_today = cost.summary(_runs, "day")
_month = cost.summary(_runs, "month")
if _runs:
    ac1, ac2 = st.columns(2)
    ac1.metric("Today", f"₹{_today['total_cost']:.2f}")
    ac2.metric("This month", f"₹{_month['total_cost']:.2f}")
    _crows = [{"model": m, "runs": b["n"], "in_tok": b["in"], "out_tok": b["out"],
               "₹": round(b["cost"], 2)} for m, b in _month["by_model"].items()]
    if _crows:
        st.dataframe(pd.DataFrame(_crows), use_container_width=True)
else:
    st.caption("No AI runs yet (mock mode is free).")

# ---- Audit ledger
with st.expander("🧾 Audit ledger (recent)", expanded=False):
    _events = audit.read_events(limit=100)
    if _events:
        st.dataframe(pd.DataFrame(_events), use_container_width=True)
    else:
        st.caption("No audit events yet.")

# ---- Behavior diagnostics
with st.expander("🧠 Behavior — disposition effect", expanded=False):
    _disp = behavior.disposition_effect(realized_trades(legs, mode=mode))
    if _disp.insufficient:
        st.caption(_disp.verdict)
    else:
        if _disp.present:
            st.warning(_disp.verdict)
        else:
            st.success(_disp.verdict)
        b1, b2, b3 = st.columns(3)
        b1.metric("Winners", f"{_disp.n_wins}",
                  help=f"avg hold {_disp.avg_hold_win_hours:.1f}h · avg ₹{_disp.avg_win:,.0f}")
        b2.metric("Losers", f"{_disp.n_losses}",
                  help=f"avg hold {_disp.avg_hold_loss_hours:.1f}h · avg ₹{_disp.avg_loss:,.0f}")
        b3.metric("Loss/Win hold ratio", f"{_disp.hold_ratio:.1f}×")

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
