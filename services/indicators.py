"""Thin wrappers over the `ta` library returning pandas Series.
Centralised so every strategy computes indicators the same way."""
from __future__ import annotations
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.trend import MACD, ADXIndicator, EMAIndicator, CCIIndicator, PSARIndicator
from ta.volatility import BollingerBands, AverageTrueRange, KeltnerChannel
from ta.volume import OnBalanceVolumeIndicator

def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    return RSIIndicator(close, window=window).rsi()

def ema(close: pd.Series, window: int) -> pd.Series:
    return EMAIndicator(close, window=window).ema_indicator()

def macd_lines(close: pd.Series):
    m = MACD(close)
    return m.macd(), m.macd_signal(), m.macd_diff()

def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return AverageTrueRange(df["high"], df["low"], df["close"], window=window).average_true_range()

def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return ADXIndicator(df["high"], df["low"], df["close"], window=window).adx()

def bollinger(close: pd.Series, window: int = 20, dev: int = 2):
    bb = BollingerBands(close, window=window, window_dev=dev)
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()

def stoch(df: pd.DataFrame):
    s = StochasticOscillator(df["high"], df["low"], df["close"])
    return s.stoch(), s.stoch_signal()

def williams_r(df: pd.DataFrame) -> pd.Series:
    return WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r()

def cci(df: pd.DataFrame) -> pd.Series:
    return CCIIndicator(df["high"], df["low"], df["close"]).cci()

def obv(df: pd.DataFrame) -> pd.Series:
    return OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()

def keltner(df: pd.DataFrame):
    k = KeltnerChannel(df["high"], df["low"], df["close"])
    return k.keltner_channel_hband(), k.keltner_channel_lband()

def psar(df: pd.DataFrame) -> pd.Series:
    return PSARIndicator(df["high"], df["low"], df["close"]).psar()
