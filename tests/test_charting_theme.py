import numpy as np
import pandas as pd
import plotly.graph_objects as go

from services import charting


def _df(n=60):
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": rng.uniform(1000, 5000, n)})


_COLORS = {"bg": "#123456", "ink": "#eeeeee", "grid": "#333333",
           "green": "#00ff00", "signal": "#ff0000", "gold": "#ffcc00",
           "accent": "#0000ff"}


def test_price_chart_applies_theme_bg():
    fig = charting.price_chart(_df(), symbol="X", colors=_COLORS)
    assert isinstance(fig, go.Figure)
    assert fig.layout.paper_bgcolor == "#123456"
    assert fig.layout.plot_bgcolor == "#123456"


def test_price_chart_backcompat_no_colors():
    fig = charting.price_chart(_df(), symbol="X")
    assert isinstance(fig, go.Figure)


def test_rsi_panel_applies_theme():
    fig = charting.rsi_panel(_df(), colors=_COLORS)
    assert fig.layout.paper_bgcolor == "#123456"


def test_macd_panel_applies_theme():
    fig = charting.macd_panel(_df(), colors=_COLORS)
    assert fig.layout.paper_bgcolor == "#123456"
