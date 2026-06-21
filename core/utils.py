"""Small shared helpers."""
from __future__ import annotations


def inr(amount: float | int | None) -> str:
    """Format a number as Indian Rupees with the Indian digit grouping.

    >>> inr(1234567.5)
    '₹12,34,567.50'
    """
    if amount is None:
        return "—"
    neg = amount < 0
    n = abs(float(amount))
    whole = int(n)
    frac = round(n - whole, 2)
    s = str(whole)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        # group the rest in 2s (Indian system)
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    else:
        grouped = s
    out = f"₹{grouped}.{int(round(frac * 100)):02d}"
    return f"-{out}" if neg else out
