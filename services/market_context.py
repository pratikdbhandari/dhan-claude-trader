"""Gather pre-market context: index regime, India VIX, index RSI state, news +
event flags. All reads are wrapped — any failure degrades that field, never raises."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from services import indicators as ind
from services import news as news_mod
from services.regime import classify_regime

log = logging.getLogger(__name__)


@dataclass
class MarketContext:
    regime: str = "UNKNOWN"
    vix: float | None = None
    index_rsi: float | None = None
    rsi_state: str = "UNKNOWN"        # OVERSOLD | OVERBOUGHT | NEUTRAL | UNKNOWN
    headlines: list[str] = field(default_factory=list)
    event_flags: list[str] = field(default_factory=list)
    as_of: str = ""


def _event_flags(headlines: list[str], today: date) -> list[str]:
    flags = []
    if today.weekday() == 3:          # Thursday = weekly index expiry
        flags.append("EXPIRY")
    blob = " ".join(headlines).lower()
    if any(k in blob for k in ("rbi", "fed", "policy", "rate decision")):
        flags.append("RBI")
    if any(k in blob for k in ("result", "earnings", "quarterly")):
        flags.append("RESULTS")
    return flags


def build_context(index_instrument, vix_instrument=None, *, dhan_client,
                  news_fetch=None, today: date | None = None) -> MarketContext:
    today = today or date.today()
    ctx = MarketContext(as_of=datetime.now().isoformat())

    try:
        candles = dhan_client.get_candles(index_instrument, interval="day",
                                          lookback_days=90)
        if len(candles) >= 30:
            ctx.regime = classify_regime(candles).value
            rsi = ind.rsi(candles["close"]).dropna()
            if len(rsi):
                ctx.index_rsi = round(float(rsi.iloc[-1]), 1)
                ctx.rsi_state = ("OVERSOLD" if ctx.index_rsi < 30
                                 else "OVERBOUGHT" if ctx.index_rsi > 70
                                 else "NEUTRAL")
    except Exception as e:            # noqa: BLE001
        log.warning("regime/rsi failed: %s", e)

    if vix_instrument is not None:
        try:
            ctx.vix = round(float(dhan_client.get_ltp(vix_instrument)), 2)
        except Exception as e:        # noqa: BLE001
            log.warning("vix fetch failed: %s", e)

    try:
        ctx.headlines = news_mod.get_headlines(index_instrument.symbol,
                                               fetch=news_fetch)
    except Exception as e:            # noqa: BLE001
        log.warning("news failed: %s", e)

    ctx.event_flags = _event_flags(ctx.headlines, today)
    return ctx
