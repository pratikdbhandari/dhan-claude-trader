"""Live Market page — real-time rates, top gainers/losers and live charts, all
from Dhan's Data APIs. Every polling partial reads the same batched, throttled
snapshot in services.market_feed, so htmx can refresh every few seconds without
tripping Dhan's 1-request/second marketfeed limit."""
from __future__ import annotations
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
        "symbols": [i.symbol for i in _chart_symbols()], "intervals": INTERVALS})


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


def _candle_fig(df, symbol: str, interval: str, sig: dict | None = None):
    import pandas as pd
    import plotly.graph_objects as go
    if "timestamp" in df.columns:
        try:
            x = pd.to_datetime(df["timestamp"], unit="s", utc=True) \
                  .dt.tz_convert("Asia/Kolkata")
        except Exception:                          # noqa: BLE001
            x = df.index
    else:
        x = df.index
    fig = go.Figure(go.Candlestick(
        x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#34d399", decreasing_line_color="#f87171",
        increasing_fillcolor="#34d399", decreasing_fillcolor="#f87171"))
    # EMA 20/50 context lines
    if len(df) >= 50:
        fig.add_trace(go.Scatter(x=x, y=ind.ema(df["close"], 20), name="EMA20",
                                 line=dict(color="#60a5fa", width=1.1)))
        fig.add_trace(go.Scatter(x=x, y=ind.ema(df["close"], 50), name="EMA50",
                                 line=dict(color="#fbbf24", width=1.1)))
    # live trade-plan levels from the confluence signal on this timeframe
    if sig and not sig["hold"]:
        for level, color, label in ((sig["entry"], "#60a5fa", "entry"),
                                    (sig["stop_loss"], "#f87171", "SL"),
                                    (sig["target"], "#34d399", "target")):
            if level is not None:
                fig.add_hline(y=level, line_color=color, line_width=1,
                              line_dash="dot",
                              annotation_text=f"{label} {level:,.2f}",
                              annotation_font_color=color,
                              annotation_position="top left")
    breaks = [dict(bounds=["sat", "mon"])]
    if interval != "day":
        breaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))  # NSE 09:15-15:30
    fig.update_layout(
        title=None, height=430, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9aa6ba", size=11),
        xaxis=dict(gridcolor="rgba(128,140,160,.12)", rangeslider_visible=False,
                   rangebreaks=breaks),
        yaxis=dict(gridcolor="rgba(128,140,160,.12)", side="right"),
        showlegend=False)
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
    return templates.TemplateResponse("partials/live_chart.html", {
        "request": request,
        "fig": fig_json(_candle_fig(df, symbol, interval, sig)),
        "symbol": symbol, "interval": interval, "last": last, "bars": len(df),
        "sig": sig})
