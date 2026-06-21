"""Map order context to an accounting segment (matches charges.json keys)."""
from __future__ import annotations


def to_segment(product_type: str, kind: str) -> str:
    k = (kind or "").upper()
    if k in ("FUT", "FUTURES"):
        return "futures"
    if k in ("OPT", "OPTION", "OPTIONS"):
        return "options"
    return "equity_intraday" if (product_type or "").upper() in ("INTRADAY", "INTRA") \
        else "equity_delivery"
