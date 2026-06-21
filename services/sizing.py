"""Confidence-based position sizing: scale the risk-budget quantity by signal
quality (and historical profit-probability when available). Big size only on
strong, clean setups; skip marginal ones. Pure + testable.

Always sits ON TOP of the 1%-risk position_size — it can only shrink or modestly
scale risk, never exceed the hard risk cap by more than the configured max."""
from __future__ import annotations

MAX_MULTIPLIER = 1.25


def quality_multiplier(quality_score: float, profit_probability: float | None = None) -> float:
    """0 (skip) to MAX_MULTIPLIER. Bands on quality; nudged by historical win-rate."""
    if quality_score < 50:
        mult = 0.0
    elif quality_score < 65:
        mult = 0.5
    elif quality_score < 80:
        mult = 1.0
    else:
        mult = MAX_MULTIPLIER

    if mult > 0 and profit_probability is not None:
        if profit_probability < 45:
            mult *= 0.5          # history says this bucket loses often → trim
        elif profit_probability >= 65:
            mult = min(MAX_MULTIPLIER, mult * 1.2)
    return round(mult, 2)


def sized_qty(base_qty: int, quality_score: float,
              profit_probability: float | None = None) -> int:
    """base_qty = the 1%-risk position_size. Returns the quality-scaled quantity."""
    return int(base_qty * quality_multiplier(quality_score, profit_probability))
