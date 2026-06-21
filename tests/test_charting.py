import numpy as np
import pandas as pd
import plotly.graph_objects as go
from services.charting import price_chart, rsi_panel, macd_panel


def _candles(n=60):
    close = 100 + np.cumsum(np.random.default_rng(3).normal(0, 1, n))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)})


def test_price_chart_returns_figure_with_traces():
    fig = price_chart(_candles(), symbol="X")
    assert isinstance(fig, go.Figure)
    names = [t.name for t in fig.data]
    assert "price" in names            # candlestick present
    assert any(n.startswith("EMA") for n in names)
    assert "vol" in names


def test_price_chart_adds_markers():
    fig = price_chart(_candles(), markers={"entry": 100, "stop_loss": 98,
                                           "target": 104})
    names = [t.name for t in fig.data]
    assert "entry" in names and "stop_loss" in names and "target" in names


def test_price_chart_omits_missing_markers():
    fig = price_chart(_candles(), markers={"entry": 100, "stop_loss": None,
                                           "target": None})
    names = [t.name for t in fig.data]
    assert "entry" in names and "stop_loss" not in names


def test_rsi_and_macd_panels():
    df = _candles()
    assert isinstance(rsi_panel(df), go.Figure)
    macd = macd_panel(df)
    assert any(t.name == "MACD" for t in macd.data)
