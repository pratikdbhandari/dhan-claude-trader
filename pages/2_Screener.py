"""Screener page — run the strategy engine across the watchlist, list current setups."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.models import Instrument, TradeMode
from services.dhan_client import DhanClient
from services import instruments
from services.screener import scan

load_dotenv()
st.set_page_config(page_title="Screener — Dhan-Claude Trader", layout="wide")
from ui import themes as _themes
_themes.apply()
st.markdown("### 🔍 Strategy Screener")

PRESETS = json.loads(Path("strategies.json").read_text())["presets"]
preset = st.selectbox("Preset", list(PRESETS.keys()), index=len(PRESETS) - 1)


@st.cache_resource
def _index():
    try:
        cache = Path("data/instrument_master.csv")
        text = cache.read_text(encoding="utf-8") if cache.exists() \
            else instruments.download_master()
        return instruments.build_index(text)
    except Exception:
        return {}


def _load_watchlist():
    data = json.loads(Path("watchlist.json").read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), kind=i.get("kind", "EQUITY"))
          for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, _index())


if st.button("Run scan"):
    dhan = DhanClient(client_id=os.getenv("DHAN_CLIENT_ID"),
                      access_token=os.getenv("DHAN_ACCESS_TOKEN"), mode=TradeMode.PAPER)

    def candles_fn(instr):
        interval = 15 if instr.kind in ("INDEX", "FUT", "OPT") else "day"
        return dhan.get_candles(instr, interval=interval, lookback_days=40)

    rows = scan(_load_watchlist(), candles_fn=candles_fn,
                active_ids=PRESETS[preset])
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.caption("No signals (or data unavailable).")
