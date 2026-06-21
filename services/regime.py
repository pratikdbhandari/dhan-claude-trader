"""Market regime classifier. ADX measures trend strength; normalised ATR
measures volatility."""
from __future__ import annotations
import pandas as pd
from core.models import Regime
from services import indicators as ind

ADX_TREND_THRESHOLD = 25.0
ATR_VOLATILE_PCT = 0.025

def classify_regime(df: pd.DataFrame) -> Regime:
    adx_val = ind.adx(df).dropna().iloc[-1]
    atr_val = ind.atr(df).dropna().iloc[-1]
    price = df["close"].iloc[-1]
    atr_pct = atr_val / price if price else 0.0
    if adx_val >= ADX_TREND_THRESHOLD:
        return Regime.TRENDING
    if atr_pct >= ATR_VOLATILE_PCT:
        return Regime.VOLATILE
    return Regime.RANGING
