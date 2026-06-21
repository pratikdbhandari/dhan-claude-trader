"""Pure charge math over the charges.json rate table. No I/O beyond loading the
table once. PAPER and LIVE compute identically; LIVE actuals override via reconcile()."""
from __future__ import annotations
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from core.models import ChargeBreakdown

_CHARGES_PATH = Path(__file__).resolve().parent.parent / "charges.json"


@lru_cache(maxsize=1)
def _rates() -> dict:
    return json.loads(_CHARGES_PATH.read_text())


def _r(x: float) -> float:
    return round(float(x), 2)


def compute(segment: str, side: str, qty: int, price: float, mode: str) -> ChargeBreakdown:
    table = _rates()
    if segment not in table:
        raise ValueError(f"Unknown segment '{segment}' (not in charges.json)")
    seg = table[segment]
    turnover = qty * price
    is_buy = side.upper() == "BUY"

    if seg["brokerage_pct"] > 0:
        brokerage = min(seg["brokerage_flat"], seg["brokerage_pct"] * turnover)
    else:
        brokerage = seg["brokerage_flat"]

    stt = (seg["stt_buy"] if is_buy else seg["stt_sell"]) * turnover
    exchange_txn = seg["exchange_txn"] * turnover
    sebi = seg["sebi"] * turnover
    stamp = seg["stamp_buy"] * turnover if is_buy else 0.0
    gst = seg["gst"] * (brokerage + exchange_txn + sebi)

    brokerage, stt, exchange_txn, sebi, stamp, gst = (
        _r(brokerage), _r(stt), _r(exchange_txn), _r(sebi), _r(stamp), _r(gst))
    total = _r(brokerage + stt + exchange_txn + sebi + stamp + gst)
    return ChargeBreakdown(brokerage, stt, exchange_txn, sebi, stamp, gst, total)


def reconcile(breakdown: ChargeBreakdown, dhan_actuals: dict) -> ChargeBreakdown:
    """Override any provided component with the broker's actual value, then
    recompute total. Unprovided components are preserved. Empty dict => no-op."""
    fields = ("brokerage", "stt", "exchange_txn", "sebi", "stamp", "gst")
    updates = {k: _r(dhan_actuals[k]) for k in fields if k in dhan_actuals}
    if not updates:
        return breakdown
    merged = replace(breakdown, **updates)
    total = _r(sum(getattr(merged, f) for f in fields))
    return replace(merged, total=total)
