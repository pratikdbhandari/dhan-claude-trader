"""Pure Plotly chart builders for the dashboard. Functions take a candle DataFrame
(+ optional overlay spec) and return a plotly Figure — no Streamlit, no rendering —
so they are unit-testable by inspecting the figure's traces."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services import indicators as ind


def price_chart(df: pd.DataFrame, *, symbol: str = "", emas=(9, 21),
                bollinger: bool = True, markers: dict | None = None) -> go.Figure:
    """Candlestick + EMA overlays + optional Bollinger bands + volume subplot +
    entry/SL/target markers. `markers` = {entry, stop_loss, target} (any may be None)."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22],
                        vertical_spacing=0.03)
    x = list(range(len(df)))
    fig.add_trace(go.Candlestick(x=x, open=df["open"], high=df["high"],
                                 low=df["low"], close=df["close"], name="price"),
                  row=1, col=1)
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
                         marker=dict(color="#3a455f")), row=2, col=1)

    markers = markers or {}
    last = len(df) - 1
    for key, color, sym in (("entry", "#34d399", "triangle-up"),
                            ("stop_loss", "#f87171", "x"),
                            ("target", "#60a5fa", "circle")):
        val = markers.get(key)
        if val is not None:
            fig.add_trace(go.Scatter(x=[last], y=[val], mode="markers",
                                     name=key, marker=dict(color=color, size=11,
                                                           symbol=sym)), row=1, col=1)
    fig.update_layout(title=symbol, template="plotly_dark", height=460,
                      xaxis_rangeslider_visible=False, showlegend=True,
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig


def rsi_panel(df: pd.DataFrame) -> go.Figure:
    rsi = ind.rsi(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=rsi, mode="lines", name="RSI",
                             line=dict(color="#8b5cf6")))
    fig.add_hline(y=70, line=dict(color="#f87171", dash="dot"))
    fig.add_hline(y=30, line=dict(color="#34d399", dash="dot"))
    fig.update_layout(template="plotly_dark", height=180, title="RSI(14)",
                      margin=dict(l=10, r=10, t=30, b=10), yaxis=dict(range=[0, 100]))
    return fig


def macd_panel(df: pd.DataFrame) -> go.Figure:
    macd, signal, hist = ind.macd_lines(df["close"])
    x = list(range(len(df)))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=hist, name="hist", marker=dict(color="#3a455f")))
    fig.add_trace(go.Scatter(x=x, y=macd, mode="lines", name="MACD",
                             line=dict(color="#60a5fa")))
    fig.add_trace(go.Scatter(x=x, y=signal, mode="lines", name="signal",
                             line=dict(color="#fbbf24")))
    fig.update_layout(template="plotly_dark", height=180, title="MACD",
                      margin=dict(l=10, r=10, t=30, b=10))
    return fig
