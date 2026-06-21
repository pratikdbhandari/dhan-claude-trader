"""Multi-instrument screener: run the strategy engine across a universe and return
the instruments that currently have a signal, ranked by confluence strength.
candles_fn is injected (live Dhan or cache) so the core is testable offline."""
from __future__ import annotations
from core.models import SignalType
from services.strategies.engine import build_confluence


def _style_for(instr) -> str:
    return "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"


def scan(instruments: list, *, candles_fn, active_ids: list[int],
         min_candles: int = 30, signals_only: bool = True) -> list[dict]:
    """candles_fn(instrument) -> DataFrame. Returns ranked rows of current setups."""
    rows = []
    for instr in instruments:
        try:
            df = candles_fn(instr)
        except Exception as e:                 # noqa: BLE001
            rows.append({"symbol": instr.symbol, "error": str(e)})
            continue
        if df is None or len(df) < min_candles:
            rows.append({"symbol": instr.symbol, "error": "insufficient candles"})
            continue
        snap = build_confluence(df, regime=None, style=_style_for(instr),
                                active_ids=active_ids)
        if signals_only and snap.bias is SignalType.HOLD:
            continue
        rows.append({
            "symbol": instr.symbol, "regime": snap.regime.value,
            "signal": snap.bias.value, "net_score": snap.net_score,
            "buy": snap.buy_count, "sell": snap.sell_count, "hold": snap.hold_count,
        })
    # rank: signalled rows first, by |net_score| desc; errors last
    return sorted(rows, key=lambda r: abs(r.get("net_score", 0)) if "error" not in r
                  else -1, reverse=True)
