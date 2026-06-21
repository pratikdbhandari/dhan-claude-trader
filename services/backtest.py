"""Pure historical-replay backtester for the mechanical technical engine.

Walks candles bar-by-bar, opens a trade on confluence bias, exits on ATR
stop/target or a time cap, deducts real charges, and reports metrics + a
calibration table (realized win-rate per setup bucket) used for an honest
Profit-Probability score. Backtests the deterministic engine only (no LLM)."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from core.models import BacktestTrade, BacktestResult, SignalType
from services import indicators as ind
from services.regime import classify_regime
from services.strategies.engine import build_confluence
from services.charges import compute


def _score_band(net: float) -> str:
    a = abs(net)
    if a >= 0.50:
        return "0.50+"
    if a >= 0.30:
        return "0.30-0.50"
    return "0.15-0.30"


def _trade_charges(segment: str, side: str, qty: int, entry: float,
                   exit_px: float) -> float:
    opp = "SELL" if side == "BUY" else "BUY"
    c1 = compute(segment, side, qty, entry, "PAPER").total
    c2 = compute(segment, opp, qty, exit_px, "PAPER").total
    return round(c1 + c2, 2)


def simulate(df: pd.DataFrame, *, active_ids: list[int], style: str,
             segment: str = "equity_intraday", atr_sl: float = 1.0,
             atr_tgt: float = 2.0, time_cap: int = 20, warmup: int = 200,
             qty: int = 1, trail_atr: float | None = None) -> BacktestResult:
    n = len(df)
    trades: list[BacktestTrade] = []
    if n <= warmup + 2:
        return _result(trades)

    atr_series = ind.atr(df)
    i = warmup
    while i < n - 1:
        window = df.iloc[:i + 1]
        snap = build_confluence(window, regime=None, style=style,
                                active_ids=active_ids)
        if snap.bias is SignalType.HOLD:
            i += 1
            continue
        atr = atr_series.iloc[i]
        if pd.isna(atr) or atr <= 0:
            i += 1
            continue
        side = "BUY" if snap.bias is SignalType.BUY else "SELL"
        entry = float(df["close"].iloc[i])
        if side == "BUY":
            stop, target = entry - atr_sl * atr, entry + atr_tgt * atr
        else:
            stop, target = entry + atr_sl * atr, entry - atr_tgt * atr

        exit_idx, exit_px, reason = i + 1, entry, "TIME"
        best = entry                      # for trailing
        for j in range(i + 1, min(i + 1 + time_cap, n)):
            hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
            if trail_atr is not None:
                # trailing stop: ratchet stop toward price; no fixed target (let it run)
                if side == "BUY":
                    if lo <= stop:
                        exit_idx, exit_px, reason = j, stop, "TRAIL"
                        break
                    best = max(best, hi)
                    stop = max(stop, best - trail_atr * atr)
                else:
                    if hi >= stop:
                        exit_idx, exit_px, reason = j, stop, "TRAIL"
                        break
                    best = min(best, lo)
                    stop = min(stop, best + trail_atr * atr)
            else:
                if side == "BUY":
                    if lo <= stop:
                        exit_idx, exit_px, reason = j, stop, "STOP"
                        break
                    if hi >= target:
                        exit_idx, exit_px, reason = j, target, "TARGET"
                        break
                else:
                    if hi >= stop:
                        exit_idx, exit_px, reason = j, stop, "STOP"
                        break
                    if lo <= target:
                        exit_idx, exit_px, reason = j, target, "TARGET"
                        break
            exit_idx, exit_px = j, float(df["close"].iloc[j])

        gross = round((exit_px - entry) * qty * (1 if side == "BUY" else -1), 2)
        charges = _trade_charges(segment, side, qty, entry, exit_px)
        trades.append(BacktestTrade(
            symbol=df.attrs.get("symbol", "?"), side=side, entry_idx=i,
            exit_idx=exit_idx, entry_price=round(entry, 2), exit_price=round(exit_px, 2),
            gross_pnl=gross, charges=charges, net_pnl=round(gross - charges, 2),
            exit_reason=reason, regime=snap.regime.value, net_score=snap.net_score))
        i = exit_idx + 1   # no pyramiding

    return _result(trades)


def _result(trades: list[BacktestTrade]) -> BacktestResult:
    n = len(trades)
    if n == 0:
        return BacktestResult([], 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [])
    wins = sum(1 for t in trades if t.net_pnl > 0)
    gross = round(sum(t.gross_pnl for t in trades), 2)
    net = round(sum(t.net_pnl for t in trades), 2)
    gprofit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gloss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    pf = round(gprofit / gloss, 2) if gloss > 0 else float("inf")
    # max drawdown on cumulative net curve
    cum, peak, mdd = 0.0, 0.0, 0.0
    for t in trades:
        cum += t.net_pnl
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return BacktestResult(
        trades=trades, n_trades=n, wins=wins, win_rate=round(wins / n * 100, 2),
        gross_pnl=gross, net_pnl=net, profit_factor=pf,
        expectancy=round(net / n, 2), max_drawdown=round(mdd, 2),
        calibration=_calibrate(trades))


def _calibrate(trades: list[BacktestTrade]) -> list[dict]:
    buckets: dict[tuple, list[BacktestTrade]] = {}
    for t in trades:
        buckets.setdefault((t.regime, _score_band(t.net_score)), []).append(t)
    out = []
    for (regime, band), ts in sorted(buckets.items()):
        wins = sum(1 for t in ts if t.net_pnl > 0)
        out.append({"regime": regime, "score_band": band, "n": len(ts),
                    "win_rate": round(wins / len(ts) * 100, 2)})
    return out


def split_eval(df: pd.DataFrame, *, train_frac: float = 0.7, **kw) -> dict:
    cut = int(len(df) * train_frac)
    return {"in_sample": simulate(df.iloc[:cut], **kw),
            "out_of_sample": simulate(df.iloc[cut:].reset_index(drop=True), **kw)}


def compare_exits(df: pd.DataFrame, *, trail_atr: float = 2.0, **kw) -> dict:
    """A/B the exit model out-of-sample: fixed stop/target vs ATR-trailing.
    Use to decide whether trailing actually improves expectancy before going live."""
    fixed = split_eval(df, trail_atr=None, **kw)
    trail = split_eval(df, trail_atr=trail_atr, **kw)
    return {"fixed": fixed, "trailing": trail}


def profit_probability(net_score: float, regime: str, calibration: list[dict],
                       min_n: int = 5) -> float | None:
    band = _score_band(net_score)
    for b in calibration:
        if b["regime"] == regime and b["score_band"] == band and b["n"] >= min_n:
            return b["win_rate"]
    return None


def score_strategies(df: pd.DataFrame, *, style: str, segment: str,
                     ids: list[int] | None = None, **kw) -> list[dict]:
    """Backtest each strategy SOLO and rank by out-of-sample expectancy. Use to
    prune consistently negative-expectancy strategies (data-driven, not opinion).
    A strategy that never fires in this data's regime shows 0 trades."""
    from services.strategies import base
    ids = ids or list(range(1, 30))
    rows = []
    for sid in ids:
        ev = split_eval(df, active_ids=[sid], style=style, segment=segment, **kw)
        ins, oos = ev["in_sample"], ev["out_of_sample"]
        spec = base.REGISTRY.get(sid)
        rows.append({
            "id": sid, "name": spec.name if spec else "?",
            "category": spec.category if spec else "?",
            "is_trades": ins.n_trades, "is_win": ins.win_rate, "is_exp": ins.expectancy,
            "oos_trades": oos.n_trades, "oos_win": oos.win_rate,
            "oos_exp": oos.expectancy, "oos_net": oos.net_pnl,
        })
    return sorted(rows, key=lambda r: r["oos_exp"], reverse=True)


def prune_candidates(scored: list[dict], min_trades: int = 5) -> list[dict]:
    """Strategies with enough samples but negative out-of-sample expectancy."""
    return [r for r in scored
            if r["oos_trades"] >= min_trades and r["oos_exp"] < 0]


def save_calibration(result: BacktestResult, path: str = "data/calibration.json") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.calibration, indent=2), encoding="utf-8")
    return str(p)
