import numpy as np
import pandas as pd
import pytest

def _ohlcv(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    rng = np.random.default_rng(42)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})

@pytest.fixture
def trending_candles():
    n = 250
    close = 100 + np.linspace(0, 40, n) + np.random.default_rng(1).normal(0, 0.5, n)
    return _ohlcv(close)

@pytest.fixture
def ranging_candles():
    n = 250
    close = 100 + 3 * np.sin(np.linspace(0, 12 * np.pi, n)) \
            + np.random.default_rng(2).normal(0, 0.3, n)
    return _ohlcv(close)
