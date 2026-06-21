"""Backtest runner — replay presets over watchlist instruments, print in-sample vs
out-of-sample metrics + calibration, write reports/backtest_<symbol>_<preset>.md.
Read-only (no orders). Needs Dhan creds (or cached CSVs in data/backtest/).
Run: python scripts_backtest.py
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from core.models import Instrument, TradeMode
from services.dhan_client import DhanClient, DhanError
from services import instruments
from services.backtest import (simulate, split_eval, save_calibration,
                               score_strategies, prune_candidates, compare_exits)
from services.backtest_data import load_candles
import services.strategies.trend          # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout        # noqa: F401
import services.strategies.volume          # noqa: F401
import services.strategies.structure       # noqa: F401

PRESETS = json.loads(Path("strategies.json").read_text())["presets"]


def _fmt(r):
    pf = "∞" if r.profit_factor == float("inf") else r.profit_factor
    return (f"trades {r.n_trades} · win {r.win_rate}% · net ₹{r.net_pnl:,.0f} · "
            f"PF {pf} · exp ₹{r.expectancy} · maxDD ₹{r.max_drawdown:,.0f}")


def main():
    client = DhanClient(client_id=os.getenv("DHAN_CLIENT_ID"),
                        access_token=os.getenv("DHAN_ACCESS_TOKEN"),
                        mode=TradeMode.PAPER)
    try:
        idx = instruments.build_index(instruments.download_master())
    except Exception:
        idx = {}
    Path("reports").mkdir(exist_ok=True)

    for raw in json.loads(Path("watchlist.json").read_text())["instruments"]:
        instr = instruments.resolve(
            Instrument(symbol=raw["symbol"], exchange_segment=raw["exchange_segment"],
                       security_id=raw.get("security_id"), kind=raw.get("kind", "EQUITY")),
            idx)
        if not instr.security_id:
            print(f"{instr.symbol}: unresolved — skip"); continue
        style = "intraday" if instr.kind in ("INDEX", "FUT", "OPT") else "positional"
        interval = 15 if style == "intraday" else "day"
        segment = ("equity_intraday" if style == "intraday" and instr.kind == "EQUITY"
                   else "equity_delivery" if instr.kind == "EQUITY"
                   else "futures" if instr.kind in ("FUT", "INDEX") else "options")
        try:
            df = load_candles(instr, interval, 365, dhan_client=client)
        except (DhanError, ValueError) as e:
            print(f"{instr.symbol}: data unavailable ({e}) — skip"); continue
        if len(df) < 220:
            print(f"{instr.symbol}: only {len(df)} candles — skip"); continue

        print(f"\n===== {instr.symbol} ({len(df)} candles) =====")
        lines = [f"# Backtest — {instr.symbol}", ""]
        for name, ids in PRESETS.items():
            ev = split_eval(df, active_ids=ids, style=style, segment=segment,
                            warmup=200, time_cap=20)
            print(f"  {name:<20} IS: {_fmt(ev['in_sample'])}")
            print(f"  {'':<20} OOS: {_fmt(ev['out_of_sample'])}")
            lines += [f"## {name}", f"- In-sample: {_fmt(ev['in_sample'])}",
                      f"- Out-of-sample: {_fmt(ev['out_of_sample'])}", ""]
        Path(f"reports/backtest_{instr.symbol}.md").write_text(
            "\n".join(lines), encoding="utf-8")
        # save calibration from full-history run of all_on
        full = simulate(df, active_ids=PRESETS["all_on"], style=style,
                        segment=segment, warmup=200)
        save_calibration(full, path=f"data/calibration_{instr.symbol}.json")

        # per-strategy scoring + prune candidates (data-driven)
        scored = score_strategies(df, style=style, segment=segment, warmup=200,
                                  time_cap=20)
        print("  --- per-strategy (ranked by OOS expectancy) ---")
        for r in scored[:5]:
            print(f"    TOP  [{r['id']:>2}] {r['name']:<22} OOS exp ₹{r['oos_exp']} "
                  f"({r['oos_trades']} trades, win {r['oos_win']}%)")
        for r in scored[-5:]:
            print(f"    LOW  [{r['id']:>2}] {r['name']:<22} OOS exp ₹{r['oos_exp']} "
                  f"({r['oos_trades']} trades, win {r['oos_win']}%)")
        prune = prune_candidates(scored)
        if prune:
            print("  PRUNE CANDIDATES (negative OOS expectancy, enough samples):")
            print("    " + ", ".join(f"{r['id']}:{r['name']}" for r in prune))
        lines.append("## Per-strategy prune candidates")
        lines.append(", ".join(f"{r['id']}:{r['name']}" for r in prune) or "none")

        # fixed vs trailing exit comparison (out-of-sample) on all_on
        cmp = compare_exits(df, active_ids=PRESETS["all_on"], style=style,
                            segment=segment, warmup=200, time_cap=20, trail_atr=2.0)
        print("  --- exit model A/B (out-of-sample) ---")
        lines.append("## Exit model A/B (out-of-sample)")
        for label in ("fixed", "trailing"):
            o = cmp[label]["out_of_sample"]
            row = (f"{label:<9} trades {o.n_trades} · win {o.win_rate}% · "
                   f"net ₹{o.net_pnl:,.0f} · exp ₹{o.expectancy} · "
                   f"PF {'∞' if o.profit_factor == float('inf') else o.profit_factor}")
            print(f"    {row}")
            lines.append(f"- {row}")
        verdict = ("trailing" if cmp["trailing"]["out_of_sample"].expectancy
                   > cmp["fixed"]["out_of_sample"].expectancy else "fixed")
        print(f"    => better OOS expectancy: {verdict}")
        lines.append(f"- Better OOS expectancy: **{verdict}**")

        Path(f"reports/backtest_{instr.symbol}.md").write_text(
            "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
