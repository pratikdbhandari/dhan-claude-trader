"""Dhan instrument-master resolver: symbol+segment -> security_id.

Downloads the Dhan scrip CSV (cached), builds a lookup index, and fills the
security_id on watchlist instruments. Network/parse failures degrade to an empty
index (instruments stay unresolved; never crash)."""
from __future__ import annotations
import csv
import io
import logging
from dataclasses import replace
from pathlib import Path
from urllib.request import urlopen
from core.models import Instrument

log = logging.getLogger(__name__)

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
_CACHE = Path("data/instrument_master.csv")

# tolerant column-name candidates (Dhan CSV headers vary by version)
_SYMBOL_COLS = ("SEM_TRADING_SYMBOL", "SYMBOL_NAME", "SEM_CUSTOM_SYMBOL",
                "SM_SYMBOL_NAME", "tradingSymbol")
_SEGMENT_COLS = ("SEM_EXM_EXCH_ID", "EXCH_ID", "SEM_SEGMENT", "exchangeSegment")
_SECID_COLS = ("SEM_SMST_SECURITY_ID", "SECURITY_ID", "securityId")


def _default_fetch(url: str) -> str:
    with urlopen(url, timeout=20) as r:        # noqa: S310
        return r.read().decode("utf-8", "ignore")


def download_master(fetch=None, path: Path | str = _CACHE) -> str:
    fetch = fetch or _default_fetch
    text = fetch(MASTER_URL)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return text


def _pick(row: dict, cols) -> str | None:
    for c in cols:
        if c in row and row[c]:
            return row[c]
    return None


def build_index(csv_text: str) -> dict[tuple[str, str], str]:
    """Map (UPPER symbol, UPPER segment) -> security_id. Best-effort over varied headers."""
    index: dict[tuple[str, str], str] = {}
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            sym = _pick(row, _SYMBOL_COLS)
            seg = _pick(row, _SEGMENT_COLS)
            sid = _pick(row, _SECID_COLS)
            if sym and seg and sid:
                index[(sym.strip().upper(), seg.strip().upper())] = str(sid).strip()
    except Exception as e:                     # noqa: BLE001
        log.warning("instrument master parse failed: %s", e)
    return index


def _seg_key(exchange_segment: str) -> str:
    # watchlist uses NSE_EQ / IDX_I etc; CSV often uses NSE / BSE / IDX. Match on prefix.
    return (exchange_segment or "").upper().split("_")[0]


def resolve(instrument: Instrument, index: dict) -> Instrument:
    if instrument.security_id:
        return instrument
    sym = instrument.symbol.upper()
    for (csym, cseg), sid in index.items():
        if csym == sym and cseg.startswith(_seg_key(instrument.exchange_segment)):
            return replace(instrument, security_id=sid)
    return instrument


def resolve_watchlist(instruments: list[Instrument], index: dict) -> list[Instrument]:
    return [resolve(i, index) for i in instruments]
