"""Thin historical-candle loader with CSV cache. Keeps the backtest core pure:
fetch once from Dhan, cache, reuse offline."""
from __future__ import annotations
from pathlib import Path
import pandas as pd


def load_candles(instrument, interval, lookback_days: int, *, dhan_client=None,
                 cache_dir: str = "data/backtest") -> pd.DataFrame:
    cache = Path(cache_dir) / f"{instrument.symbol}_{interval}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    if dhan_client is None:
        raise ValueError("no cache and no dhan_client to fetch candles")
    df = dhan_client.get_candles(instrument, interval=interval,
                                 lookback_days=lookback_days)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df
