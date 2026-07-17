"""Live Market page — real-time rates, top gainers/losers and live charts, all
from Dhan's Data APIs. Every polling partial reads the same batched, throttled
snapshot in services.market_feed, so htmx can refresh every few seconds without
tripping Dhan's 1-request/second marketfeed limit."""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.models import Instrument, SignalType
from services import global_markets
from services import indicators as ind
from services import market_clock, market_feed, signal_engine
from services.dhan_client import DhanError
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401 - register strategies
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401
from web import deps
from web.charts import fig_json
from web.server import templates

log = logging.getLogger(__name__)
router = APIRouter()

# Index security IDs verified against the Dhan instrument master (NSE/BSE, seg I).
INDICES = [
    Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13", kind="INDEX"),
    Instrument(symbol="BANKNIFTY", exchange_segment="IDX_I", security_id="25", kind="INDEX"),
    Instrument(symbol="FINNIFTY", exchange_segment="IDX_I", security_id="27", kind="INDEX"),
    Instrument(symbol="MIDCPNIFTY", exchange_segment="IDX_I", security_id="442", kind="INDEX"),
    Instrument(symbol="SENSEX", exchange_segment="IDX_I", security_id="51", kind="INDEX"),
]

INTERVALS = [("5", "5 min"), ("15", "15 min"), ("60", "1 hour"), ("day", "Daily")]


def _dedupe(*groups: list[Instrument]) -> list[Instrument]:
    seen, out = set(), []
    for g in groups:
        for i in g:
            key = (i.exchange_segment, str(i.security_id))
            if i.security_id and key not in seen:
                seen.add(key)
                out.append(i)
    return out


def _snapshot():
    """One batched call covering indices + watchlist + movers universe."""
    watch = deps.load_watchlist()
    uni = market_feed.load_universe()
    everything = _dedupe(INDICES, watch, uni)
    sdk = deps.get_dhan().sdk
    rows = market_feed.fetch_snapshot(sdk, everything)
    return rows, watch, uni


def _market_status() -> dict:
    now = datetime.now(timezone.utc)
    is_open = market_clock.is_market_open(now)
    mins = market_clock.minutes_to_open(now)
    return {"open": is_open,
            "label": "LIVE · market open" if is_open
            else (f"closed · opens in {mins // 60}h {mins % 60}m" if mins is not None
                  else "closed")}


def _chart_symbols() -> list[Instrument]:
    return _dedupe(INDICES, deps.load_watchlist(), market_feed.load_universe())


@router.get("/live", response_class=HTMLResponse)
def live(request: Request):
    return templates.TemplateResponse("live.html", {
        "request": request, "status": _market_status(),
        "symbols": [i.symbol for i in _chart_symbols()], "intervals": INTERVALS,
        "tok": deps.get_token_status()})


@router.get("/live/partials/ticker", response_class=HTMLResponse)
def ticker(request: Request):
    rows, *_ = _snapshot()
    quotes = market_feed.quotes_for(rows, INDICES)
    return templates.TemplateResponse("partials/live_ticker.html", {
        "request": request, "quotes": quotes, "status": _market_status(),
        "feed": market_feed.staleness()})


@router.get("/live/partials/watch", response_class=HTMLResponse)
def watch(request: Request):
    rows, watch_list, _ = _snapshot()
    quotes = market_feed.quotes_for(rows, watch_list)
    return templates.TemplateResponse("partials/live_watch.html", {
        "request": request, "quotes": quotes,
        "feed": market_feed.staleness()})


@router.get("/live/partials/global", response_class=HTMLResponse)
def global_partial(request: Request):
    rows = global_markets.snapshot()
    flows = global_markets.fii_dii()
    return templates.TemplateResponse("partials/live_global.html", {
        "request": request, "groups": global_markets.grouped(rows),
        "risk": global_markets.risk_sentiment(rows), "flows": flows})


@router.get("/live/partials/movers", response_class=HTMLResponse)
def movers(request: Request):
    rows, _, uni = _snapshot()
    quotes = market_feed.quotes_for(rows, uni)
    gainers, losers = market_feed.movers(quotes, n=5)
    return templates.TemplateResponse("partials/live_movers.html", {
        "request": request, "gainers": gainers, "losers": losers,
        "scanned": len(quotes)})


def chart_signal(instr, df, interval: str) -> dict | None:
    """Confluence + mock consensus on the charted timeframe, for overlays and
    the badge. None when there's not enough data (never raises into the UI)."""
    if df is None or len(df) < 30:
        return None
    try:
        style = "positional" if interval == "day" else "intraday"
        snap = build_confluence(df, regime=None, style=style,
                                active_ids=list(range(1, 30)))
        last = float(df["close"].iloc[-1])
        atr = float(ind.atr(df).dropna().iloc[-1])
        cs = signal_engine.generate(instr, snap, last_price=last, atr=atr,
                                    mode="mock", cache={})
        sd = cs.indicator_snapshot
        return {"signal": cs.consensus.value, "confidence": cs.avg_confidence,
                "regime": snap.regime.value, "net_score": snap.net_score,
                "entry": sd.get("entry"), "stop_loss": sd.get("stop_loss"),
                "target": sd.get("target"),
                "hold": cs.consensus is SignalType.HOLD}
    except Exception:                              # noqa: BLE001
        return None


def _chart_x(df):
    """Candle timestamps in IST; falls back to the positional index."""
    import pandas as pd
    if "timestamp" in df.columns:
        try:
            return pd.to_datetime(df["timestamp"], unit="s", utc=True) \
                     .dt.tz_convert("Asia/Kolkata")
        except Exception:                          # noqa: BLE001
            pass
    return df.index


# Rolling confluence is ~55ms/bar, so marking 40 bars costs ~2s — far too slow
# for the chart's 60s refresh. The flip points only move when a new bar closes,
# so key the cache on the bar count and recompute once per bar instead.
_marker_cache: dict[tuple, list] = {}
_MARKER_BARS = 40


def signal_markers(instr, df, style: str) -> list[dict]:
    """Bars where the confluence bias flipped into BUY or SELL, over the last
    ~40 bars. These are the same engine the cards and analysis page use — not a
    cheaper lookalike — so an arrow here means what the rest of the app means."""
    key = (instr.exchange_segment, str(instr.security_id), style, len(df))
    hit = _marker_cache.get(key)
    if hit is not None:
        return hit
    out: list[dict] = []
    try:
        x = _chart_x(df)
        start = max(30, len(df) - _MARKER_BARS)
        prev = None
        for i in range(start, len(df)):
            bias = build_confluence(df.iloc[:i + 1], regime=None, style=style,
                                    active_ids=list(range(1, 30))).bias
            if prev is not None and bias is not prev and bias is not SignalType.HOLD:
                out.append({"x": x.iloc[i] if hasattr(x, "iloc") else x[i],
                            "low": float(df["low"].iloc[i]),
                            "high": float(df["high"].iloc[i]),
                            "side": bias.value})
            prev = bias
    except Exception:                              # noqa: BLE001 - chart must still render
        log.warning("signal markers failed", exc_info=True)
        out = []
    _marker_cache.clear()          # only ever need the current bar's answer
    _marker_cache[key] = out
    return out


# TradingView-ish palette. Deliberately identical in light and dark themes:
# these hues read on both, and the panels keep a transparent background so the
# page's own theme shows through.
_UP, _DOWN = "#26a69a", "#ef5350"
_GRID = "rgba(128,140,160,.10)"


def _candle_fig(df, symbol: str, interval: str, sig: dict | None = None,
                markers: list[dict] | None = None):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    x = _chart_x(df)
    close, vol = df["close"], df.get("volume")
    has_vol = vol is not None and float(vol.fillna(0).sum()) > 0

    rows = 3 if has_vol else 2
    heights = [0.62, 0.16, 0.22] if has_vol else [0.74, 0.26]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=heights)

    # ---- price ----
    fig.add_trace(go.Candlestick(
        x=x, open=df["open"], high=df["high"], low=df["low"], close=close,
        name=symbol, increasing_line_color=_UP, decreasing_line_color=_DOWN,
        increasing_fillcolor=_UP, decreasing_fillcolor=_DOWN,
        line=dict(width=1), whiskerwidth=0.6), row=1, col=1)

    if len(df) >= 20:
        fig.add_trace(go.Scatter(x=x, y=ind.ema(close, 20), name="EMA 20",
                                 line=dict(color="#2962ff", width=1.2),
                                 hovertemplate="EMA20 %{y:,.2f}<extra></extra>"),
                      row=1, col=1)
    if len(df) >= 50:
        fig.add_trace(go.Scatter(x=x, y=ind.ema(close, 50), name="EMA 50",
                                 line=dict(color="#ff9800", width=1.2),
                                 hovertemplate="EMA50 %{y:,.2f}<extra></extra>"),
                      row=1, col=1)

    # ---- buy/sell flip arrows ----
    for side, sym, colour, anchor, off in (
            ("BUY", "triangle-up", _UP, "low", -1),
            ("SELL", "triangle-down", _DOWN, "high", 1)):
        pts = [m for m in (markers or []) if m["side"] == side]
        if not pts:
            continue
        pad = (float(df["high"].max()) - float(df["low"].min())) * 0.02
        fig.add_trace(go.Scatter(
            x=[m["x"] for m in pts],
            y=[m[anchor] + off * pad for m in pts],
            mode="markers", name=side, legendgroup=side,
            marker=dict(symbol=sym, size=11, color=colour,
                        line=dict(width=1, color="rgba(255,255,255,.65)")),
            hovertemplate=f"{side} signal<extra></extra>"), row=1, col=1)

    # ---- trade plan levels ----
    if sig and not sig["hold"]:
        for level, colour, label in ((sig["entry"], "#2962ff", "Entry"),
                                     (sig["stop_loss"], _DOWN, "SL"),
                                     (sig["target"], _UP, "Target")):
            if level is not None:
                fig.add_hline(y=level, line_color=colour, line_width=1,
                              line_dash="dash", row=1, col=1,
                              annotation_text=f" {label} {level:,.2f} ",
                              annotation_font=dict(color="#fff", size=9),
                              annotation_bgcolor=colour,
                              annotation_position="right")

    # ---- last price tag ----
    last = float(close.iloc[-1])
    up = last >= float(df["open"].iloc[-1])
    fig.add_hline(y=last, line_color=_UP if up else _DOWN, line_width=1,
                  line_dash="dot", row=1, col=1,
                  annotation_text=f" {last:,.2f} ",
                  annotation_font=dict(color="#fff", size=10),
                  annotation_bgcolor=_UP if up else _DOWN,
                  annotation_position="right")

    # ---- volume ----
    if has_vol:
        colours = [_UP if c >= o else _DOWN
                   for c, o in zip(close, df["open"])]
        fig.add_trace(go.Bar(x=x, y=vol, name="Volume", marker_color=colours,
                             marker_line_width=0, opacity=0.5,
                             hovertemplate="Vol %{y:,.0f}<extra></extra>"),
                      row=2, col=1)

    # ---- RSI ----
    rsi_row = 3 if has_vol else 2
    rsi = ind.rsi(close)
    fig.add_trace(go.Scatter(x=x, y=rsi, name="RSI 14",
                             line=dict(color="#b388ff", width=1.2),
                             hovertemplate="RSI %{y:.1f}<extra></extra>"),
                  row=rsi_row, col=1)
    for lvl, dash in ((70, "dash"), (30, "dash"), (50, "dot")):
        fig.add_hline(y=lvl, line_color="rgba(128,140,160,.35)", line_width=1,
                      line_dash=dash, row=rsi_row, col=1)

    # ---- layout ----
    breaks = [dict(bounds=["sat", "mon"])]
    if interval != "day":
        breaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))  # NSE 09:15-15:30
    spike = dict(showspikes=True, spikemode="across", spikesnap="cursor",
                 spikethickness=1, spikedash="dot",
                 spikecolor="rgba(128,140,160,.55)")
    fig.update_layout(
        height=560, margin=dict(l=8, r=64, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9aa6ba", size=11),
        dragmode="pan", hovermode="x unified", bargap=0.2,
        hoverlabel=dict(bgcolor="rgba(19,24,34,.92)", font_size=11,
                        bordercolor="rgba(128,140,160,.3)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left",
                    x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        xaxis_rangeslider_visible=False)
    fig.update_xaxes(gridcolor=_GRID, rangebreaks=breaks, showline=False,
                     zeroline=False, **spike)
    fig.update_yaxes(gridcolor=_GRID, side="right", zeroline=False,
                     showspikes=True, spikemode="across", spikesnap="cursor",
                     spikethickness=1, spikedash="dot",
                     spikecolor="rgba(128,140,160,.55)")
    fig.update_yaxes(tickformat=",.2f", row=1, col=1)
    if has_vol:
        fig.update_yaxes(showgrid=False, tickformat=".2s", row=2, col=1)
    fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70], row=rsi_row, col=1)
    return fig


@router.get("/live/partials/chart", response_class=HTMLResponse)
def chart(request: Request, symbol: str = "NIFTY", interval: str = "15"):
    instr = next((i for i in _chart_symbols() if i.symbol == symbol), None)
    if instr is None:
        return HTMLResponse('<div class="banner err">Unknown symbol.</div>')
    if interval not in {v for v, _ in INTERVALS}:
        interval = "15"
    dhan = deps.get_dhan()
    lookback = 180 if interval == "day" else (5 if interval in ("15", "60") else 2)
    try:
        df = deps.fetch_candles(dhan, instr,
                                interval=interval if interval == "day" else int(interval),
                                lookback_days=lookback,
                                ttl=600.0 if interval == "day" else 55.0)
    except DhanError as e:
        return HTMLResponse(f'<div class="banner err">Chart data failed: {e}</div>')
    if df is None or df.empty:
        return HTMLResponse('<div class="banner warn">No candle data returned '
                            'for this symbol/interval.</div>')
    last = float(df["close"].iloc[-1])
    sig = chart_signal(instr, df, interval)
    style = "positional" if interval == "day" else "intraday"
    markers = signal_markers(instr, df, style) if len(df) >= 31 else []
    return templates.TemplateResponse("partials/live_chart.html", {
        "request": request,
        "fig": fig_json(_candle_fig(df, symbol, interval, sig, markers)),
        "symbol": symbol, "interval": interval, "last": last, "bars": len(df),
        "sig": sig})
