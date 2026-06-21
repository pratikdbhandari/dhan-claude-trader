"""Run eligible strategies and aggregate votes with CATEGORY weighting so that
many correlated indicators in one category cannot fake conviction.

net_score = mean over categories of (category net score), where a category's
score is the strength-weighted mean of its members' signed votes (BUY=+1,
SELL=-1, HOLD=0), normalised to [-1, 1]. Equal weight per category =>
decorrelation across indicator families."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from core.models import ConfluenceSnapshot, Regime, SignalType, StrategyVote
from services.regime import classify_regime
from services.strategies import base

_SIGN = {SignalType.BUY: 1.0, SignalType.SELL: -1.0, SignalType.HOLD: 0.0}
BUY_THRESHOLD = 0.15
SELL_THRESHOLD = -0.15


def build_confluence(df: pd.DataFrame, *, regime: Optional[Regime],
                     style: str, active_ids: list[int]) -> ConfluenceSnapshot:
    regime = regime or classify_regime(df)
    specs = [s for s in base.eligible(regime=regime.value, style=style)
             if s.id in active_ids]
    votes: list[StrategyVote] = [s.run(df) for s in specs]

    by_cat: dict[str, list[StrategyVote]] = {}
    for v in votes:
        by_cat.setdefault(v.category, []).append(v)

    category_scores: dict[str, float] = {}
    for cat, vs in by_cat.items():
        wsum = sum(v.strength for v in vs) or 1
        score = sum(_SIGN[v.vote] * v.strength for v in vs) / wsum
        category_scores[cat] = max(-1.0, min(1.0, score))

    net = (sum(category_scores.values()) / len(category_scores)) if category_scores else 0.0
    if net >= BUY_THRESHOLD:
        bias = SignalType.BUY
    elif net <= SELL_THRESHOLD:
        bias = SignalType.SELL
    else:
        bias = SignalType.HOLD

    return ConfluenceSnapshot(
        regime=regime, votes=votes, category_scores=category_scores,
        net_score=round(net, 4), bias=bias,
        buy_count=sum(1 for v in votes if v.vote is SignalType.BUY),
        sell_count=sum(1 for v in votes if v.vote is SignalType.SELL),
        hold_count=sum(1 for v in votes if v.vote is SignalType.HOLD),
    )
