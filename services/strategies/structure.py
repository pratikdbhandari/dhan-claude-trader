"""Multi-timeframe / structure strategies 28-29.
Strategy 28 expects df.attrs['daily'] (a daily DataFrame) when available;
falls back to single-timeframe bias if absent."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy


@strategy(id=28, name="mtf_alignment", category="structure", regimes=("TRENDING", "VOLATILE"), intraday_only=False)
def mtf_alignment(df):
    intraday_bias = ind.ema(df["close"], 21).iloc[-1] < df["close"].iloc[-1]
    daily = df.attrs.get("daily")
    if daily is not None and len(daily) > 21:
        daily_bias = ind.ema(daily["close"], 21).iloc[-1] < daily["close"].iloc[-1]
        if intraday_bias and daily_bias:
            return SignalType.BUY, 72, "15m & daily both bullish"
        if not intraday_bias and not daily_bias:
            return SignalType.SELL, 72, "15m & daily both bearish"
        return SignalType.HOLD, 0, "timeframes disagree"
    return (SignalType.BUY, 50, "intraday bullish (no daily)") if intraday_bias \
        else (SignalType.SELL, 50, "intraday bearish (no daily)")


@strategy(id=29, name="pivot_sr", category="structure", regimes=("RANGING", "VOLATILE"), intraday_only=True)
def pivot_sr(df):
    if len(df) < 2:
        return SignalType.HOLD, 0, "insufficient data"
    h, l, c = df["high"].iloc[-2], df["low"].iloc[-2], df["close"].iloc[-2]
    pivot = (h + l + c) / 3
    s1, r1 = 2 * pivot - h, 2 * pivot - l
    price = df["close"].iloc[-1]
    if price <= s1:
        return SignalType.BUY, 60, "bounced off S1"
    if price >= r1:
        return SignalType.SELL, 60, "rejected at R1"
    return SignalType.HOLD, 0, "between pivots"
