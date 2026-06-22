"""Settings page — enter all API keys/tokens in-app (no file editing), test them,
and get a Dhan token. Saves to ~/.dhan_claude_trader/settings.local.json (local,
never in Git). The installed app reads keys from here first, then .env."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st

from core import config_store
from core.models import Instrument, TradeMode
from services.dhan_client import DhanClient
from services import instruments, selftest

st.set_page_config(page_title="Settings — Dhan-Claude Trader", layout="wide")
st.markdown("### ⚙️ Settings — API Keys & Connection")
st.caption("Keys are saved locally on this PC only (never uploaded / never in Git).")

cur = config_store.load()


def val(k, default=""):
    return cur.get(k, "") or default


# ---------------------------------------------------------------- Dhan
st.markdown("#### 🔑 Dhan")
st.link_button("Get Dhan Token  ↗", "https://web.dhan.co/",
               help="Opens Dhan. Go to Profile → DhanHQ Trading APIs → Generate "
                    "Access Token, then paste below.")
c1, c2 = st.columns(2)
dhan_id = c1.text_input("Dhan Client ID", value=val("DHAN_CLIENT_ID"))
dhan_tok = c2.text_input("Dhan Access Token", value=val("DHAN_ACCESS_TOKEN"),
                         type="password")
trade_mode = st.selectbox("Trade mode", ["PAPER", "LIVE"],
                          index=0 if val("TRADE_MODE", "PAPER") == "PAPER" else 1)

# ---------------------------------------------------------------- AI
st.markdown("#### 🤖 AI Providers")
a1, a2 = st.columns(2)
anthropic_k = a1.text_input("Anthropic (Claude) key", value=val("ANTHROPIC_API_KEY"),
                            type="password")
groq_k = a2.text_input("Groq key", value=val("GROQ_API_KEY"), type="password")
cerebras_k = a1.text_input("Cerebras key", value=val("CEREBRAS_API_KEY"), type="password")
mistral_k = a2.text_input("Mistral key", value=val("MISTRAL_API_KEY"), type="password")
signal_source = st.selectbox("Signal source", ["mock", "api"],
                             index=0 if val("SIGNAL_SOURCE", "mock") == "mock" else 1,
                             help="mock = free, deterministic. api = call the AI keys above.")

# ---------------------------------------------------------------- Risk
st.markdown("#### 🛡️ Risk limits")
r1, r2, r3, r4 = st.columns(4)
max_loss = r1.number_input("Max daily loss ₹", value=float(val("MAX_DAILY_LOSS", "10000")))
risk_pct = r2.number_input("Risk % per trade", value=float(val("MAX_RISK_PER_TRADE_PCT", "1.0")))
max_pos = r3.number_input("Max open positions", value=int(float(val("MAX_OPEN_POSITIONS", "2"))))
capital = r4.number_input("Account capital ₹ (paper)", value=float(val("ACCOUNT_CAPITAL", "100000")))

# ---------------------------------------------------------------- Save
if st.button("💾 Save settings", type="primary"):
    path = config_store.save({
        "DHAN_CLIENT_ID": dhan_id, "DHAN_ACCESS_TOKEN": dhan_tok,
        "ANTHROPIC_API_KEY": anthropic_k, "GROQ_API_KEY": groq_k,
        "CEREBRAS_API_KEY": cerebras_k, "MISTRAL_API_KEY": mistral_k,
        "SIGNAL_SOURCE": signal_source, "TRADE_MODE": trade_mode,
        "MAX_DAILY_LOSS": max_loss, "MAX_RISK_PER_TRADE_PCT": risk_pct,
        "MAX_OPEN_POSITIONS": max_pos, "ACCOUNT_CAPITAL": capital,
    })
    st.success(f"Saved to {path}")

st.divider()

# ---------------------------------------------------------------- Test All
if st.button("🔌 Test All connections"):
    rows = []
    # Dhan (read-only) — uses just-entered values
    try:
        client = DhanClient(client_id=dhan_id, access_token=dhan_tok,
                            mode=TradeMode.PAPER)
        try:
            idx = instruments.build_index(instruments.download_master())
        except Exception:
            idx = {}
        eq = instruments.resolve(Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                                            security_id=None, kind="EQUITY"), idx)
        index = instruments.resolve(Instrument(symbol="NIFTY", exchange_segment="IDX_I",
                                               security_id=None, kind="INDEX"), idx)
        rows += selftest.test_dhan(client, eq, index)
    except Exception as e:                     # noqa: BLE001
        from services.connectivity import Check
        rows.append(Check("Dhan client", "FAIL", str(e)))

    # AI providers
    keymap = {"ANTHROPIC_API_KEY": anthropic_k, "GROQ_API_KEY": groq_k,
              "CEREBRAS_API_KEY": cerebras_k, "MISTRAL_API_KEY": mistral_k}
    if signal_source == "api":
        specs = json.loads(Path("providers.json").read_text())["providers"]
        rows += selftest.test_providers(specs, key_lookup=lambda e: keymap.get(e))
    # data sources
    rows += selftest.test_data_sources()

    df = pd.DataFrame([{"check": c.name, "status": c.status, "detail": c.detail}
                       for c in rows])
    st.dataframe(df, use_container_width=True)
    fails = [c for c in rows if c.status == "FAIL"]
    if fails:
        st.error(f"{len(fails)} check(s) failed — fix before live trading.")
    else:
        st.success("All checks passed (skipped = key not set).")
