"""Breakout / volatility strategies 18-23. Eligible in VOLATILE & TRENDING."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_BO = ("VOLATILE", "TRENDING")


@strategy(id=18, name="bb_squeeze_breakout", category="breakout", regimes=_BO, intraday_only=False)
def bb_squeeze(df):
    hi, mid, lo = ind.bollinger(df["close"])
    width = (hi - lo) / mid
    narrow = width.iloc[-1] <= width.rolling(50).quantile(0.25).iloc[-1]
    c = df["close"].iloc[-1]
    if narrow and c >= hi.iloc[-1]:
        return SignalType.BUY, 70, "squeeze breakout up"
    if narrow and c <= lo.iloc[-1]:
        return SignalType.SELL, 70, "squeeze breakout down"
    return SignalType.HOLD, 0, "no squeeze breakout"


@strategy(id=19, name="donchian_breakout", category="breakout", regimes=_BO, intraday_only=False)
def donchian(df, window=20):
    hh = df["high"].rolling(window).max().iloc[-2]
    ll = df["low"].rolling(window).min().iloc[-2]
    c = df["close"].iloc[-1]
    if c > hh:
        return SignalType.BUY, 68, "Donchian upper breakout"
    if c < ll:
        return SignalType.SELL, 68, "Donchian lower breakout"
    return SignalType.HOLD, 0, "inside channel"


@strategy(id=20, name="opening_range_breakout", category="breakout", regimes=_BO, intraday_only=True)
def orb(df, n=15):
    opening = df.iloc[:n]
    or_high, or_low = opening["high"].max(), opening["low"].min()
    c = df["close"].iloc[-1]
    if c > or_high:
        return SignalType.BUY, 66, "ORB up"
    if c < or_low:
        return SignalType.SELL, 66, "ORB down"
    return SignalType.HOLD, 0, "inside opening range"


@strategy(id=21, name="atr_expansion", category="breakout", regimes=_BO, intraday_only=False)
def atr_expansion(df):
    atr = ind.atr(df)
    expanding = atr.iloc[-1] > atr.rolling(20).mean().iloc[-1] * 1.3
    if not expanding:
        return SignalType.HOLD, 0, "no ATR expansion"
    up = df["close"].iloc[-1] > df["close"].iloc[-2]
    return (SignalType.BUY, 64, "ATR expansion up") if up else (SignalType.SELL, 64, "ATR expansion down")


@strategy(id=22, name="prev_day_break", category="breakout", regimes=_BO, intraday_only=False)
def prev_day_break(df):
    if len(df) < 2:
        return SignalType.HOLD, 0, "insufficient data"
    pdh, pdl = df["high"].iloc[-2], df["low"].iloc[-2]
    c = df["close"].iloc[-1]
    if c > pdh:
        return SignalType.BUY, 60, "broke previous high"
    if c < pdl:
        return SignalType.SELL, 60, "broke previous low"
    return SignalType.HOLD, 0, "within previous range"


@strategy(id=23, name="keltner_breakout", category="breakout", regimes=_BO, intraday_only=False)
def keltner(df):
    hi, lo = ind.keltner(df)
    c = df["close"].iloc[-1]
    if c > hi.iloc[-1]:
        return SignalType.BUY, 62, "Keltner upper breakout"
    if c < lo.iloc[-1]:
        return SignalType.SELL, 62, "Keltner lower breakout"
    return SignalType.HOLD, 0, "inside Keltner"
