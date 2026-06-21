"""Mean-reversion strategies 10-17. Eligible mainly in RANGING."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_MR = ("RANGING",)


@strategy(id=10, name="rsi_extremes", category="mean_reversion", regimes=_MR, intraday_only=False)
def rsi_extremes(df):
    r = ind.rsi(df["close"]).iloc[-1]
    if r < 30:
        return SignalType.BUY, 68, f"RSI oversold ({r:.0f})"
    if r > 70:
        return SignalType.SELL, 68, f"RSI overbought ({r:.0f})"
    return SignalType.HOLD, 0, f"RSI neutral ({r:.0f})"


@strategy(id=11, name="rsi_divergence", category="mean_reversion", regimes=_MR, intraday_only=False)
def rsi_divergence(df, lb=14):
    r = ind.rsi(df["close"])
    price, rsi_s = df["close"], r
    p_low_now, p_low_prev = price.iloc[-1], price.iloc[-lb]
    r_low_now, r_low_prev = rsi_s.iloc[-1], rsi_s.iloc[-lb]
    if p_low_now < p_low_prev and r_low_now > r_low_prev:
        return SignalType.BUY, 64, "bullish RSI divergence"
    if p_low_now > p_low_prev and r_low_now < r_low_prev:
        return SignalType.SELL, 64, "bearish RSI divergence"
    return SignalType.HOLD, 0, "no divergence"


@strategy(id=12, name="bollinger_reversal", category="mean_reversion", regimes=_MR, intraday_only=False)
def bb_reversal(df):
    hi, mid, lo = ind.bollinger(df["close"])
    c = df["close"].iloc[-1]
    if c <= lo.iloc[-1]:
        return SignalType.BUY, 66, "tagged lower band"
    if c >= hi.iloc[-1]:
        return SignalType.SELL, 66, "tagged upper band"
    return SignalType.HOLD, 0, "inside bands"


@strategy(id=13, name="stoch_cross", category="mean_reversion", regimes=_MR, intraday_only=False)
def stoch_cross(df):
    k, d = ind.stoch(df)
    if k.iloc[-1] < 20 and k.iloc[-1] > d.iloc[-1] and k.iloc[-2] <= d.iloc[-2]:
        return SignalType.BUY, 63, "stochastic bullish cross in oversold"
    if k.iloc[-1] > 80 and k.iloc[-1] < d.iloc[-1] and k.iloc[-2] >= d.iloc[-2]:
        return SignalType.SELL, 63, "stochastic bearish cross in overbought"
    return SignalType.HOLD, 0, "no stoch signal"


@strategy(id=14, name="williams_r", category="mean_reversion", regimes=_MR, intraday_only=False)
def williams(df):
    w = ind.williams_r(df).iloc[-1]
    if w < -80:
        return SignalType.BUY, 60, "Williams %R oversold"
    if w > -20:
        return SignalType.SELL, 60, "Williams %R overbought"
    return SignalType.HOLD, 0, "neutral"


@strategy(id=15, name="cci_extremes", category="mean_reversion", regimes=_MR, intraday_only=False)
def cci_extremes(df):
    c = ind.cci(df).iloc[-1]
    if c < -100:
        return SignalType.BUY, 60, "CCI < -100"
    if c > 100:
        return SignalType.SELL, 60, "CCI > 100"
    return SignalType.HOLD, 0, "CCI neutral"


@strategy(id=16, name="vwap_reversion", category="mean_reversion", regimes=_MR, intraday_only=True)
def vwap_reversion(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    diff = (df["close"].iloc[-1] - vwap.iloc[-1]) / vwap.iloc[-1]
    if diff < -0.005:
        return SignalType.BUY, 58, "below VWAP, revert up"
    if diff > 0.005:
        return SignalType.SELL, 58, "above VWAP, revert down"
    return SignalType.HOLD, 0, "near VWAP"


@strategy(id=17, name="zscore_mean", category="mean_reversion", regimes=_MR, intraday_only=False)
def zscore(df, window=20):
    c = df["close"]
    mean = c.rolling(window).mean().iloc[-1]
    std = c.rolling(window).std().iloc[-1] or 1e-9
    z = (c.iloc[-1] - mean) / std
    if z < -2:
        return SignalType.BUY, 62, f"z-score {z:.1f} (cheap)"
    if z > 2:
        return SignalType.SELL, 62, f"z-score {z:.1f} (rich)"
    return SignalType.HOLD, 0, f"z-score {z:.1f}"
