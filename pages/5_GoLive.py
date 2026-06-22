"""Go-Live Readiness — tracks the 5 gates that must pass before real-money trading.
LIVE mode stays locked on the dashboard until all five are checked here."""
from __future__ import annotations
import os
import streamlit as st
from dotenv import load_dotenv

from core import readiness, config_store
from core.models import Instrument, TradeMode
from services.dhan_client import DhanClient
from services import instruments, selftest

load_dotenv()
st.set_page_config(page_title="Go-Live — Dhan-Claude Trader", layout="wide")
from ui import themes as _themes
_themes.apply()

st.markdown("<div class='eyebrow'>SAFETY</div>"
            "<div class='page-title'>Go-Live Readiness</div>"
            "<div class='page-desc'>Real-money LIVE mode is locked until all five gates pass. "
            "This is deliberate — most retail F&O loses; prove it first.</div>",
            unsafe_allow_html=True)

done = readiness.passed_count()
total = len(readiness.GATE_IDS)
st.progress(done / total, text=f"{done}/{total} gates passed")
if readiness.all_passed():
    st.success("✅ All gates passed — LIVE trading is unlocked on the dashboard.")
else:
    st.warning(f"🔒 LIVE locked — {total - done} gate(s) remaining.")

st.divider()
state = readiness.get_state()

for gid, label, kind in readiness.GATES:
    cols = st.columns([0.08, 0.72, 0.20])
    checked = bool(state.get(gid))
    cols[0].markdown("✅" if checked else "⬜")
    cols[1].markdown(f"**{label}**  \n<span class='muted'>{kind}</span>",
                     unsafe_allow_html=True)
    new = cols[2].checkbox("Passed", value=checked, key=f"gate_{gid}")
    if new != checked:
        readiness.set_gate(gid, new)
        st.rerun()

st.divider()
st.markdown("<div class='eyebrow'>AUTO-VERIFY</div>", unsafe_allow_html=True)
st.caption("Run the read-only connectivity self-test; it auto-checks the connectivity gate.")
if st.button("🔌 Run connectivity self-test"):
    cid = config_store.get_setting("DHAN_CLIENT_ID")
    if not cid or cid == "your_dhan_client_id":
        st.error("No Dhan creds — enter them on the Settings page first.")
    else:
        client = DhanClient(client_id=cid,
                            access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                            mode=TradeMode.PAPER)
        try:
            idx = instruments.build_index(instruments.download_master())
        except Exception:
            idx = {}
        eq = instruments.resolve(Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                                            security_id=None, kind="EQUITY"), idx)
        index = instruments.resolve(Instrument(symbol="NIFTY", exchange_segment="IDX_I",
                                               security_id=None, kind="INDEX"), idx)
        rows = selftest.test_dhan(client, eq, index)
        import pandas as pd
        st.dataframe(pd.DataFrame([{"check": c.name, "status": c.status,
                                    "detail": c.detail} for c in rows]),
                     use_container_width=True)
        if not any(c.status == "FAIL" for c in rows):
            readiness.set_gate("connectivity", True)
            st.success("Connectivity gate auto-passed.")
            st.rerun()
        else:
            st.error("Connectivity has failures — fix before passing this gate.")
