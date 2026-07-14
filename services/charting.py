"""Pure Plotly chart builders for the dashboard. Functions take a candle DataFrame
(+ optional overlay spec) and return a plotly Figure — no Streamlit, no rendering —
so they are unit-testable by inspecting the figure's traces."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services import indicators as ind

_DEFAULT_COLORS = {"bg": "#0e1117", "ink": "#e6e9ef", "grid": "#232936",
                   "green": "#34d399", "signal": "#f87171", "gold": "#fbbf24",
                   "accent": "#60a5fa"}


def _theme_layout(colors: dict | None) -> dict:
    c = colors or _DEFAULT_COLORS
    return dict(paper_bgcolor=c["bg"], plot_bgcolor=c["bg"],
                font=dict(color=c["ink"]),
                xaxis=dict(gridcolor=c["grid"]), yaxis=dict(gridcolor=c["grid"]),
                margin=dict(l=8, r=8, t=8, b=8), showlegend=True,
                legend=dict(font=dict(size=10)))


def price_chart(df: pd.DataFrame, *, symbol: str = "", emas=(9, 21),
                bollinger: bool = True, markers: dict | None = None,
                colors: dict | None = None) -> go.Figure:
    """Candlestick + EMA overlays + optional Bollinger bands + volume subplot +
    entry/SL/target markers. `markers` = {entry, stop_loss, target} (any may be None).
    `colors` = theme palette from themes.chart_colors(); None => default dark look."""
    c = colors or _DEFAULT_COLORS
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
                        vertical_spacing=0.03)
    x = list(range(len(df)))
    fig.add_trace(go.Candlestick(x=x, open=df["open"], high=df["high"],
                                 low=df["low"], close=df["close"], name="price",
                                 increasing_line_color=c["green"],
                                 decreasing_line_color=c["signal"]), row=1, col=1)
    for w in emas:
        if len(df) > w:
            fig.add_trace(go.Scatter(x=x, y=ind.ema(df["close"], w), mode="lines",
                                     name=f"EMA{w}", line=dict(width=1)), row=1, col=1)
    if bollinger and len(df) > 20:
        hi, mid, lo = ind.bollinger(df["close"])
        fig.add_trace(go.Scatter(x=x, y=hi, mode="lines", name="BB up",
                                 line=dict(width=1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=lo, mode="lines", name="BB low",
                                 line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=df["volume"], name="vol",
                         marker=dict(color=c["grid"])), row=2, col=1)

    markers = markers or {}
    last = len(df) - 1
    for key, color, sym in (("entry", c["green"], "triangle-up"),
                            ("stop_loss", c["signal"], "x"),
                            ("target", c["accent"], "circle")):
        val = markers.get(key)
        if val is not None:
            fig.add_trace(go.Scatter(x=[last], y=[val], mode="markers",
                                     name=key, marker=dict(color=color, size=11,
                                                           symbol=sym)), row=1, col=1)
    fig.update_layout(height=460, xaxis_rangeslider_visible=False,
                      **_theme_layout(colors))
    return fig


def rsi_panel(df: pd.DataFrame, colors: dict | None = None) -> go.Figure:
    c = colors or _DEFAULT_COLORS
    rsi = ind.rsi(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=rsi, mode="lines", name="RSI",
                             line=dict(color=c["accent"])))
    fig.add_hline(y=70, line=dict(color=c["signal"], dash="dot"))
    fig.add_hline(y=30, line=dict(color=c["green"], dash="dot"))
    lay = _theme_layout(colors)
    lay["yaxis"] = dict(range=[0, 100], gridcolor=c["grid"])
    fig.update_layout(height=180, **lay)
    return fig


def macd_panel(df: pd.DataFrame, colors: dict | None = None) -> go.Figure:
    c = colors or _DEFAULT_COLORS
    macd, signal, hist = ind.macd_lines(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=hist, name="hist", marker=dict(color=c["grid"])))
    fig.add_trace(go.Scatter(x=x, y=macd, mode="lines", name="MACD",
                             line=dict(color=c["accent"])))
    fig.add_trace(go.Scatter(x=x, y=signal, mode="lines", name="signal",
                             line=dict(color=c["gold"])))
    fig.update_layout(height=180, **_theme_layout(colors))
    return fig
