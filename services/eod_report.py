"""End-of-day report: summary, per-provider accuracy leaderboard, detailed trades.
Writes dated Markdown + CSV to reports/. Pure-ish over a journal connection."""
from __future__ import annotations
import csv
import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path
from data.journal import stats, list_trades, to_legs
from services.accounting import pnl_statement

log = logging.getLogger(__name__)


def _leaderboard(closed: list[dict]) -> list[dict]:
    """From each closed trade's consensus_json, score each provider against the
    winning direction (trade side if pnl>0 else opposite). HOLD excluded."""
    tally: dict[str, dict] = defaultdict(lambda: {"calls": 0, "correct": 0})
    for t in closed:
        pnl = t.get("pnl")
        if pnl is None or pnl == 0:
            continue
        cj = t.get("consensus_json")
        if not cj:
            continue
        try:
            data = json.loads(cj)
        except (json.JSONDecodeError, TypeError):
            continue
        side = (t.get("side") or "").upper()
        winning = side if pnl > 0 else ("SELL" if side == "BUY" else "BUY")
        for p in (data.get("providers") or []):
            psig = str(p.get("signal", "")).upper()
            if psig not in ("BUY", "SELL"):
                continue
            name = p.get("provider", "?")
            tally[name]["calls"] += 1
            if psig == winning:
                tally[name]["correct"] += 1
    out = []
    for name, d in sorted(tally.items()):
        acc = round(100 * d["correct"] / d["calls"], 1) if d["calls"] else 0.0
        out.append({"provider": name, "calls": d["calls"],
                    "correct": d["correct"], "accuracy": acc})
    return out


def build_report(journal_conn, mode: str, date_key: str | None = None,
                 ltp_fn=None) -> dict:
    s = stats(journal_conn, mode)
    legs = to_legs(journal_conn, mode)
    stmt = pnl_statement(legs, mode=mode, period="all", period_key=None,
                         ltp_fn=ltp_fn or (lambda sym: None))
    all_trades = list_trades(journal_conn, mode=mode)
    closed = [t for t in all_trades if t.get("pnl") is not None]
    summary = {
        "trades": s["trades"], "wins": s["wins"], "win_rate": s["win_rate"],
        "net_pnl": stmt.total_pnl, "avg_rr_predicted": s["avg_rr_predicted"],
        "avg_rr_achieved": s["avg_rr_achieved"],
    }
    return {
        "mode": mode, "date": date_key or date.today().isoformat(),
        "summary": summary, "leaderboard": _leaderboard(closed), "detailed": closed,
    }


def write_report(report: dict, out_dir: str | Path = "reports",
                 date_key: str | None = None) -> tuple[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dk = date_key or report["date"]
    mode = report["mode"]
    md_path = out / f"EOD_{dk}_{mode}.md"
    csv_path = out / f"EOD_{dk}_{mode}.csv"

    s = report["summary"]
    lines = [
        f"# EOD Report — {dk} — {mode}", "",
        "## Summary", "",
        f"- Trades: {s['trades']}  ·  Wins: {s['wins']}  ·  Win rate: {s['win_rate']}%",
        f"- Net P&L: ₹{s['net_pnl']:,.2f}",
        f"- Avg R:R predicted: {s['avg_rr_predicted']}  ·  achieved: {s['avg_rr_achieved']}",
        "", "## Provider Leaderboard", "",
        "| Provider | Calls | Correct | Accuracy |",
        "|---|---|---|---|",
    ]
    for r in report["leaderboard"]:
        lines.append(f"| {r['provider']} | {r['calls']} | {r['correct']} | {r['accuracy']}% |")
    if not report["leaderboard"]:
        lines.append("| _no scored calls_ | 0 | 0 | 0% |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cols = ["symbol", "side", "qty", "entry", "exec_price", "exit_price", "pnl",
            "rr_predicted", "rr_achieved", "signal", "confidence"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for t in report["detailed"]:
            w.writerow([t.get(c) for c in cols])
    return str(md_path), str(csv_path)
