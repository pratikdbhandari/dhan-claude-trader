"""Transparent rule map: MarketContext -> recommended preset + reasons + cautions.
Deterministic and testable; the AI only narrates, it does not decide here."""
from __future__ import annotations
from dataclasses import dataclass, field
from services.market_context import MarketContext

VIX_LOW = 15.0
VIX_HIGH = 20.0
VIX_VERY_HIGH = 25.0


@dataclass
class Selection:
    preset: str
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    extra_notes: list[str] = field(default_factory=list)


_EVENT_CAUTION = {
    "EXPIRY": "Expiry day — avoid fresh naked positions, expect theta/whipsaw.",
    "RBI": "Policy/RBI event — expect volatility spikes and whipsaws.",
    "RESULTS": "Earnings/results in news — single-stock event risk.",
}


def select(ctx: MarketContext) -> Selection:
    reasons = [f"Regime: {ctx.regime}"]
    if ctx.index_rsi is not None:
        reasons.append(f"Index RSI {ctx.index_rsi} ({ctx.rsi_state})")
    if ctx.vix is not None:
        reasons.append(f"India VIX {ctx.vix}")

    cautions: list[str] = []
    extra: list[str] = []
    very_high_vix = ctx.vix is not None and ctx.vix > VIX_VERY_HIGH
    high_vix = ctx.vix is not None and ctx.vix > VIX_HIGH
    low_vix = ctx.vix is not None and ctx.vix < VIX_LOW

    # priority: extreme volatility > rsi extremes > regime
    if ctx.regime == "VOLATILE" or very_high_vix:
        preset = "range_scalper"
        cautions.append("Elevated volatility — defined-risk only, consider sitting out.")
    elif ctx.rsi_state in ("OVERSOLD", "OVERBOUGHT"):
        preset = "range_scalper"
        bias = "long" if ctx.rsi_state == "OVERSOLD" else "short"
        reasons.append(f"RSI extreme -> mean-reversion {bias} bias")
    elif ctx.regime == "TRENDING":
        preset = "intraday_momentum"
        if high_vix:
            cautions.append("High VIX — size down on momentum entries.")
        if low_vix:
            extra.append("Low VIX + trending: also a good day for positional_quality (equities).")
    elif ctx.regime == "RANGING":
        preset = "range_scalper"
    else:  # UNKNOWN
        preset = "range_scalper"
        cautions.append("Regime unknown (data issue) — defaulting to conservative range play.")

    for f in ctx.event_flags:
        if f in _EVENT_CAUTION:
            cautions.append(_EVENT_CAUTION[f])

    return Selection(preset=preset, reasons=reasons, cautions=cautions, extra_notes=extra)
