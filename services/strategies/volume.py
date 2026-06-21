"""Volume strategies 24-27."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_ALL = ("TRENDING", "RANGING", "VOLATILE")


@strategy(id=24, name="volume_spike", category="volume", regimes=_ALL, intraday_only=False)
def volume_spike(df):
    avg = df["volume"].rolling(20).mean().iloc[-1]
    spike = df["volume"].iloc[-1] > 1.5 * avg
    if not spike:
        return SignalType.HOLD, 0, "no volume spike"
    up = df["close"].iloc[-1] > df["close"].iloc[-2]
    return (SignalType.BUY, 60, "volume spike up") if up else (SignalType.SELL, 60, "volume spike down")


@strategy(id=25, name="obv_trend", category="volume", regimes=_ALL, intraday_only=False)
def obv_trend(df):
    o = ind.obv(df)
    rising = o.iloc[-1] > o.rolling(20).mean().iloc[-1]
    return (SignalType.BUY, 58, "OBV rising") if rising else (SignalType.SELL, 58, "OBV falling")


@strategy(id=26, name="vwap_cross", category="volume", regimes=_ALL, intraday_only=True)
def vwap_cross(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    c, cp = df["close"].iloc[-1], df["close"].iloc[-2]
    if c > vwap.iloc[-1] and cp <= vwap.iloc[-2]:
        return SignalType.BUY, 62, "crossed above VWAP"
    if c < vwap.iloc[-1] and cp >= vwap.iloc[-2]:
        return SignalType.SELL, 62, "crossed below VWAP"
    return SignalType.HOLD, 0, "no VWAP cross"


@strategy(id=27, name="volume_weighted_breakout", category="volume", regimes=("TRENDING", "VOLATILE"), intraday_only=False)
def vw_breakout(df, window=20):
    hh = df["high"].rolling(window).max().iloc[-2]
    avg = df["volume"].rolling(window).mean().iloc[-1]
    if df["close"].iloc[-1] > hh and df["volume"].iloc[-1] > 1.5 * avg:
        return SignalType.BUY, 66, "breakout on high volume"
    return SignalType.HOLD, 0, "no volume-confirmed breakout"
