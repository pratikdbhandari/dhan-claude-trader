import importlib
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _ensure_strategies_registered():
    """Repopulate the strategy REGISTRY before every test.

    test_strategy_base.py calls REGISTRY.clear(), which (depending on file
    order) would otherwise leave later strategy tests with an empty registry.
    Reloading re-runs the @strategy decorators so the 29 strategies are present
    for any test that needs them; tests that deliberately clear still run after
    this fixture, so their assertions are unaffected.
    """
    from services.strategies import base
    for mod in ("trend", "mean_reversion", "breakout", "volume", "structure"):
        try:
            m = importlib.import_module(f"services.strategies.{mod}")
            importlib.reload(m)
        except Exception:
            pass
    yield


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
