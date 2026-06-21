"""Trend / momentum strategies 1-9. Eligible mainly in TRENDING (some in VOLATILE)."""
from __future__ import annotations
import pandas as pd
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_TREND = ("TRENDING", "VOLATILE")


@strategy(id=1, name="ema_cross_9_21", category="trend", regimes=_TREND, intraday_only=False)
def ema_cross(df):
    fast, slow = ind.ema(df["close"], 9), ind.ema(df["close"], 21)
    if fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-2] <= slow.iloc[-2]:
        return SignalType.BUY, 70, "9EMA crossed above 21EMA"
    if fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-2] >= slow.iloc[-2]:
        return SignalType.SELL, 70, "9EMA crossed below 21EMA"
    bias = SignalType.BUY if fast.iloc[-1] > slow.iloc[-1] else SignalType.SELL
    return bias, 55, "EMA alignment (no fresh cross)"


@strategy(id=2, name="ema_ribbon", category="trend", regimes=_TREND, intraday_only=False)
def ema_ribbon(df):
    es = [ind.ema(df["close"], w).iloc[-1] for w in (8, 13, 21, 34, 55)]
    if all(es[i] > es[i + 1] for i in range(len(es) - 1)):
        return SignalType.BUY, 75, "EMA ribbon stacked bullish"
    if all(es[i] < es[i + 1] for i in range(len(es) - 1)):
        return SignalType.SELL, 75, "EMA ribbon stacked bearish"
    return SignalType.HOLD, 0, "ribbon mixed"


@strategy(id=3, name="macd_signal_cross", category="trend", regimes=_TREND, intraday_only=False)
def macd_cross(df):
    macd, sig, _ = ind.macd_lines(df["close"])
    if macd.iloc[-1] > sig.iloc[-1] and macd.iloc[-2] <= sig.iloc[-2]:
        return SignalType.BUY, 70, "MACD crossed above signal"
    if macd.iloc[-1] < sig.iloc[-1] and macd.iloc[-2] >= sig.iloc[-2]:
        return SignalType.SELL, 70, "MACD crossed below signal"
    return SignalType.HOLD, 0, "no MACD cross"


@strategy(id=4, name="macd_hist_momentum", category="trend", regimes=_TREND, intraday_only=False)
def macd_hist(df):
    _, _, hist = ind.macd_lines(df["close"])
    if hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
        return SignalType.BUY, 60, "MACD histogram rising +ve"
    if hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
        return SignalType.SELL, 60, "MACD histogram falling -ve"
    return SignalType.HOLD, 0, "histogram flat"


@strategy(id=5, name="adx_di_cross", category="trend", regimes=_TREND, intraday_only=False)
def adx_di(df):
    from ta.trend import ADXIndicator
    a = ADXIndicator(df["high"], df["low"], df["close"])
    adx_v, pos, neg = a.adx().iloc[-1], a.adx_pos().iloc[-1], a.adx_neg().iloc[-1]
    if adx_v < 25:
        return SignalType.HOLD, 0, "ADX weak (<25)"
    return (SignalType.BUY, 72, "ADX strong, +DI>-DI") if pos > neg else \
           (SignalType.SELL, 72, "ADX strong, -DI>+DI")


@strategy(id=6, name="supertrend", category="trend", regimes=_TREND, intraday_only=False)
def supertrend(df, period=10, mult=3.0):
    atr = ind.atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    lower = hl2 - mult * atr
    close = df["close"]
    direction = close.iloc[-1] > lower.iloc[-1]
    prev = close.iloc[-2] > lower.iloc[-2]
    if direction and not prev:
        return SignalType.BUY, 73, "Supertrend flipped up"
    if not direction and prev:
        return SignalType.SELL, 73, "Supertrend flipped down"
    return (SignalType.BUY, 58, "Supertrend up") if direction else (SignalType.SELL, 58, "Supertrend down")


@strategy(id=7, name="psar_flip", category="trend", regimes=_TREND, intraday_only=False)
def psar_flip(df):
    ps = ind.psar(df)
    below = df["close"].iloc[-1] > ps.iloc[-1]
    prev_below = df["close"].iloc[-2] > ps.iloc[-2]
    if below and not prev_below:
        return SignalType.BUY, 65, "PSAR flipped bullish"
    if not below and prev_below:
        return SignalType.SELL, 65, "PSAR flipped bearish"
    return (SignalType.BUY, 55, "PSAR bullish") if below else (SignalType.SELL, 55, "PSAR bearish")


@strategy(id=8, name="price_vs_200ema", category="trend", regimes=("TRENDING", "RANGING", "VOLATILE"), intraday_only=False)
def price_vs_200(df):
    e = ind.ema(df["close"], min(200, len(df) - 1))
    return (SignalType.BUY, 60, "price above 200EMA") if df["close"].iloc[-1] > e.iloc[-1] \
        else (SignalType.SELL, 60, "price below 200EMA")


@strategy(id=9, name="market_structure", category="trend", regimes=_TREND, intraday_only=False)
def market_structure(df, lookback=20):
    recent = df.iloc[-lookback:]
    hh = recent["high"].iloc[-1] >= recent["high"].max() * 0.999
    ll = recent["low"].iloc[-1] <= recent["low"].min() * 1.001
    if hh:
        return SignalType.BUY, 62, "fresh higher-high"
    if ll:
        return SignalType.SELL, 62, "fresh lower-low"
    return SignalType.HOLD, 0, "inside structure"
