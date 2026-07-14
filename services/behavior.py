"""Trading-behavior diagnostics over closed trades. Pure: RealizedTrade list in,
DispositionResult out. First diagnostic: the disposition effect (holding losers
longer than winners). Concept adapted from the Vibe-Trading project; implemented
fresh in this repo's style."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from core.models import RealizedTrade

MIN_SAMPLE = 3


@dataclass
class DispositionResult:
    n_wins: int
    n_losses: int
    avg_hold_win_hours: float
    avg_hold_loss_hours: float
    avg_win: float
    avg_loss: float
    hold_ratio: float
    present: bool
    insufficient: bool
    verdict: str


def _hold_hours(trade: RealizedTrade) -> float | None:
    try:
        o = datetime.fromisoformat(trade.opened_at)
        c = datetime.fromisoformat(trade.closed_at)
    except (ValueError, TypeError):
        return None
    return (c - o).total_seconds() / 3600.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def disposition_effect(trades: list[RealizedTrade]) -> DispositionResult:
    win_holds: list[float] = []
    loss_holds: list[float] = []
    wins: list[float] = []
    losses: list[float] = []
    for t in trades:
        h = _hold_hours(t)
        if h is None:
            continue
        if t.net_pnl > 0:
            win_holds.append(h)
            wins.append(t.net_pnl)
        elif t.net_pnl < 0:
            loss_holds.append(h)
            losses.append(-t.net_pnl)

    n_wins, n_losses = len(wins), len(losses)
    avg_hold_win = round(_mean(win_holds), 2)
    avg_hold_loss = round(_mean(loss_holds), 2)
    avg_win = round(_mean(wins), 2)
    avg_loss = round(_mean(losses), 2)

    if n_wins < MIN_SAMPLE or n_losses < MIN_SAMPLE:
        return DispositionResult(
            n_wins=n_wins, n_losses=n_losses, avg_hold_win_hours=avg_hold_win,
            avg_hold_loss_hours=avg_hold_loss, avg_win=avg_win, avg_loss=avg_loss,
            hold_ratio=0.0, present=False, insufficient=True,
            verdict=(f"Not enough closed trades yet (need >={MIN_SAMPLE} wins and "
                     f">={MIN_SAMPLE} losses) to assess disposition effect."))

    hold_ratio = round(avg_hold_loss / avg_hold_win, 2) if avg_hold_win > 0 else 0.0
    present = avg_hold_loss > avg_hold_win
    if present:
        verdict = (f"Disposition effect detected: losers held {avg_hold_loss:.1f}h vs "
                   f"winners {avg_hold_win:.1f}h ({hold_ratio:.1f}x longer). You tend "
                   f"to ride losers and cut winners.")
    else:
        verdict = (f"No disposition effect: winners held {avg_hold_win:.1f}h vs losers "
                   f"{avg_hold_loss:.1f}h - you are not systematically riding losers.")

    return DispositionResult(
        n_wins=n_wins, n_losses=n_losses, avg_hold_win_hours=avg_hold_win,
        avg_hold_loss_hours=avg_hold_loss, avg_win=avg_win, avg_loss=avg_loss,
        hold_ratio=hold_ratio, present=present, insufficient=False, verdict=verdict)
