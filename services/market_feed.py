"""Batched live market-data feed over Dhan's marketfeed REST API.

Dhan throttles the marketfeed endpoints (ltp/ohlc/quote) to ~1 request/second,
but one batch call accepts up to 1000 instruments. So every caller goes through
a single throttled, TTL-cached snapshot: one ohlc_data call covers the index
strip, the live watchlist table and the movers universe together. UI partials
can poll every few seconds — at most one broker call per TTL window is made,
and while throttled the last snapshot is served stale rather than erroring.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.models import Instrument

log = logging.getLogger(__name__)

# minimum spacing between calls to Dhan marketfeed (their limit is ~1/sec)
_MIN_CALL_GAP = 1.2

# Serving a stale snapshot is correct for a throttled second, but past this the
# prices on screen are no longer the market's — the UI must say so out loud.
STALE_AFTER = 30.0

_lock = threading.Lock()
# ts/monotonic drives the TTL; ok_wall is wall-clock of the last SUCCESSFUL
# refresh, used to age the snapshot for the UI.
_cache: dict = {"key": None, "ts": 0.0, "rows": {}, "ok_wall": 0.0}
_last_call_ts = 0.0


@dataclass(frozen=True)
class Quote:
    symbol: str
    security_id: str
    exchange_segment: str
    kind: str
    ltp: float
    prev_close: float
    open: float
    high: float
    low: float

    @property
    def change(self) -> float:
        return round(self.ltp - self.prev_close, 2)

    @property
    def pct(self) -> float:
        if not self.prev_close:
            return 0.0
        return round((self.ltp - self.prev_close) / self.prev_close * 100, 2)


def securities_map(instruments: list[Instrument]) -> dict[str, list[int]]:
    """Group resolved instruments into the {segment: [ids]} shape ohlc_data wants."""
    out: dict[str, list[int]] = {}
    for i in instruments:
        if not i.security_id:
            continue
        out.setdefault(i.exchange_segment, []).append(int(i.security_id))
    return out


def _extract_rows(resp) -> dict[tuple[str, str], dict]:
    """Flatten the (sometimes doubly nested) marketfeed response into
    {(segment, security_id): row}. Returns {} on any unexpected shape."""
    if not isinstance(resp, dict):
        return {}
    data = resp.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    rows: dict[tuple[str, str], dict] = {}
    if not isinstance(data, dict):
        return rows
    for seg, by_id in data.items():
        if not isinstance(by_id, dict):
            continue
        for sid, row in by_id.items():
            if isinstance(row, dict):
                rows[(str(seg), str(sid))] = row
    return rows


def fetch_snapshot(sdk, instruments: list[Instrument], *, ttl: float = 3.0,
                   now: Optional[float] = None) -> dict[tuple[str, str], dict]:
    """Raw rows keyed by (segment, security_id), from cache when fresh.

    One ohlc_data call refreshes everything; between the TTL and the 1/sec
    throttle window the previous snapshot is returned unchanged (never raises
    into the UI — an empty dict means "no data yet")."""
    global _last_call_ts
    secs = securities_map(instruments)
    key = tuple(sorted((s, tuple(sorted(ids))) for s, ids in secs.items()))
    t = time.monotonic() if now is None else now
    with _lock:
        fresh = _cache["key"] == key and (t - _cache["ts"]) < ttl
        throttled = (t - _last_call_ts) < _MIN_CALL_GAP
        if fresh or (throttled and _cache["key"] == key):
            return _cache["rows"]
        _last_call_ts = t
        try:
            resp = sdk.ohlc_data(secs)
            rows = _extract_rows(resp)
        except Exception:                          # noqa: BLE001 - stale beats crash
            log.exception("marketfeed ohlc_data failed")
            rows = {}
        if rows:
            _cache.update(key=key, ts=t, rows=rows, ok_wall=time.time())
            return rows
        # failed/empty: keep serving the previous snapshot if it was for this key
        # (ok_wall deliberately untouched, so staleness() ages it)
        return _cache["rows"] if _cache["key"] == key else {}


def staleness(now: Optional[float] = None) -> dict:
    """How old the on-screen prices are: seconds since the last SUCCESSFUL
    marketfeed refresh, a stale flag, and the last-update clock for the UI.
    `stale` is True before the first success (nothing real has arrived yet)."""
    with _lock:
        ok = _cache["ok_wall"]
    if not ok:
        return {"age": None, "stale": True, "last": None}
    age = (time.time() if now is None else now) - ok
    return {"age": int(age), "stale": age > STALE_AFTER,
            "last": time.strftime("%H:%M:%S", time.localtime(ok))}


def quotes_for(rows: dict[tuple[str, str], dict],
               instruments: list[Instrument]) -> list[Quote]:
    """Join raw snapshot rows back onto instruments (skips ones with no data).
    During a live session marketfeed's ohlc.close is the previous day's close."""
    out = []
    for i in instruments:
        row = rows.get((i.exchange_segment, str(i.security_id)))
        if not row:
            continue
        ohlc = row.get("ohlc") or {}
        ltp = row.get("last_price")
        if not isinstance(ltp, (int, float)):
            continue
        out.append(Quote(
            symbol=i.symbol, security_id=str(i.security_id),
            exchange_segment=i.exchange_segment, kind=i.kind,
            ltp=float(ltp),
            prev_close=float(ohlc.get("close") or 0),
            open=float(ohlc.get("open") or 0),
            high=float(ohlc.get("high") or 0),
            low=float(ohlc.get("low") or 0)))
    return out


def movers(quotes: list[Quote], n: int = 5) -> tuple[list[Quote], list[Quote]]:
    """(top gainers, top losers) by % change over prev close; equities only."""
    eq = [q for q in quotes if q.kind == "EQUITY" and q.prev_close > 0]
    ranked = sorted(eq, key=lambda q: q.pct, reverse=True)
    gainers = [q for q in ranked[:n] if q.pct > 0]
    losers = [q for q in ranked[::-1][:n] if q.pct < 0]
    return gainers, losers


def load_universe(path: str | Path = "universe.json") -> list[Instrument]:
    """The movers universe (NIFTY-50 constituents with pre-verified security IDs).
    Missing file degrades to an empty universe, never a crash."""
    try:
        data = json.loads(Path(path).read_text())
    except Exception:                              # noqa: BLE001
        log.warning("universe file %s missing/unreadable", path)
        return []
    return [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                       security_id=i.get("security_id"),
                       lot_size=i.get("lot_size", 1),
                       kind=i.get("kind", "EQUITY"))
            for i in data.get("instruments", [])]
