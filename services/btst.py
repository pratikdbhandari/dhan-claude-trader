"""Buy-Today-Sell-Tomorrow candidate scan. Pure: candles + confluence in,
ranked BtstCandidate list out. candles_fn / confluence_fn are injected so the
core is testable offline (live wiring is done by the page)."""
from __future__ import annotations
from core.models import BtstCandidate, SignalType
from services.indicators import atr

CLOSE_STRENGTH_MIN = 0.7
VOLUME_RATIO_MIN = 1.2
TARGET_ATR_MULT = 1.5
STOP_ATR_MULT = 1.0
GAP_RISK_NOTE = ("Overnight gap risk: no stop protection while the market is "
                 "shut; a gap-down can breach the planned stop at the open.")


def _close_strength(row) -> float:
    rng = float(row["high"]) - float(row["low"])
    if rng <= 0:
        return 0.0
    return (float(row["close"]) - float(row["low"])) / rng


def scan(instruments: list, *, candles_fn, confluence_fn, active_ids: list[int],
         avg_vol_lookback: int = 20) -> list[BtstCandidate]:
    out: list[BtstCandidate] = []
    for instr in instruments:
        try:
            df = candles_fn(instr)
        except Exception:                          # noqa: BLE001 - skip, not fatal
            continue
        if df is None or len(df) < avg_vol_lookback + 1:
            continue
        last = df.iloc[-1]
        snap = confluence_fn(df)

        if snap.bias is not SignalType.BUY or snap.net_score <= 0:
            continue
        cs = _close_strength(last)
        if cs < CLOSE_STRENGTH_MIN:
            continue
        avg_vol = float(df["volume"].iloc[-(avg_vol_lookback + 1):-1].mean())
        vol_ratio = float(last["volume"]) / avg_vol if avg_vol > 0 else 0.0
        if vol_ratio < VOLUME_RATIO_MIN:
            continue
        if float(last["close"]) <= float(last["open"]):
            continue

        entry = float(last["close"])
        a = float(atr(df).dropna().iloc[-1])
        target = round(entry + TARGET_ATR_MULT * a, 2)
        stop = round(entry - STOP_ATR_MULT * a, 2)
        reasons = [
            f"close in top {round((1 - cs) * 100)}% of day range (strength {cs:.2f})",
            f"volume {vol_ratio:.2f}x average",
            "green daily candle",
            f"bullish confluence (net {snap.net_score:.2f})",
        ]
        out.append(BtstCandidate(
            instrument=instr, entry=entry, target=target, stop=stop,
            net_score=snap.net_score, close_strength=round(cs, 2),
            volume_ratio=round(vol_ratio, 2), reasons=reasons,
            gap_risk=GAP_RISK_NOTE))

    out.sort(key=lambda c: c.net_score * c.close_strength, reverse=True)
    return out
