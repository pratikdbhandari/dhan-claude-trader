"""Shared helpers for web routes — mirror the wiring app.py does, reading creds from
config_store (never os.getenv). Daily lookback is 400 so the engine has enough bars."""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path

from core import config_store
from core.models import Instrument, TradeMode
from data.journal import init_db
from services import instruments, risk_manager
from services.dhan_client import DhanClient, DhanError

_journal = None
_index: dict | None = None


def get_journal():
    global _journal
    if _journal is None:
        _journal = init_db("trades.db")
    return _journal


def get_mode() -> str:
    return config_store.get_setting("TRADE_MODE", "PAPER")


def get_dhan(mode: str | None = None) -> DhanClient:
    mode = mode or get_mode()
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


def get_token_status():
    """Pre-flight: will the saved Dhan token survive the next session? No network."""
    from services.connectivity import token_status
    return token_status(config_store.get_setting("DHAN_ACCESS_TOKEN"))


def get_risk_config():
    return risk_manager.load_risk_config({
        "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
        "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
        "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
    })


def _instrument_index() -> dict:
    global _index
    if _index is not None:
        return _index
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
               else instruments.download_master())
        _index = instruments.build_index(text)
    except Exception:                              # noqa: BLE001
        _index = {}
    return _index


def load_watchlist(path: str | Path = "watchlist.json") -> list[Instrument]:
    data = json.loads(Path(path).read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY")) for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, _instrument_index())


def get_equity(mode: str, dhan) -> float:
    if mode == "LIVE":
        try:
            f = dhan.get_fund_limits()
            return float(f.get("availabelBalance", f.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


def style_for(kind: str) -> str:
    return "intraday" if kind in ("INDEX", "FUT", "OPT") else "positional"


# Candle cache: Dhan's historical Data API rate-limits rapid sequential calls
# (empty responses after ~4-5 back-to-back requests), so cache per
# (instrument, interval) and space out real broker calls. Shared by the signal
# loop (candles_for) and the live chart partial (fetch_candles).
_candle_cache: dict[tuple, tuple[float, object]] = {}
_candle_lock = threading.Lock()
_last_candle_call = 0.0
_CANDLE_GAP = 0.35          # min seconds between historical API calls
_TTL = {"intraday": 120.0, "positional": 600.0}


def fetch_candles(dhan, instr, *, interval, lookback_days, ttl: float,
                  min_rows: int = 30):
    """Throttled + TTL-cached candle fetch; serves the stale frame when Dhan
    returns an empty (rate-limited) response."""
    global _last_candle_call
    key = (instr.exchange_segment, str(instr.security_id), str(interval))
    now = time.monotonic()
    with _candle_lock:
        hit = _candle_cache.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
        wait = _CANDLE_GAP - (time.monotonic() - _last_candle_call)
        if wait > 0:
            time.sleep(wait)
        _last_candle_call = time.monotonic()
        df = dhan.get_candles(instr, interval=interval, lookback_days=lookback_days)
        if df is not None and len(df) >= min_rows:
            _candle_cache[key] = (time.monotonic(), df)
        elif hit is not None:
            return hit[1]           # throttled/empty response: serve stale
        return df


def candles_for(dhan, instr):
    style = style_for(instr.kind)
    return fetch_candles(dhan, instr,
                         interval=15 if style == "intraday" else "day",
                         lookback_days=10 if style == "intraday" else 400,
                         ttl=_TTL[style])
