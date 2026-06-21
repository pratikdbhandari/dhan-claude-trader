"""Strategy registry. Each strategy is a function (df)->(SignalType, strength, detail),
wrapped with metadata. The engine runs only regime/style-eligible strategies."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import pandas as pd
from core.models import SignalType, StrategyVote

VoteFn = Callable[[pd.DataFrame], tuple]

@dataclass
class StrategySpec:
    id: int
    name: str
    category: str
    regimes: tuple[str, ...]
    intraday_only: bool
    fn: VoteFn

    def run(self, df: pd.DataFrame) -> StrategyVote:
        vote, strength, detail = self.fn(df)
        return StrategyVote(strategy_id=self.id, name=self.name,
                            category=self.category, vote=vote,
                            strength=int(strength), detail=detail)

REGISTRY: dict[int, StrategySpec] = {}

def strategy(*, id: int, name: str, category: str,
             regimes: tuple[str, ...], intraday_only: bool):
    def deco(fn: VoteFn) -> VoteFn:
        REGISTRY[id] = StrategySpec(id, name, category, regimes, intraday_only, fn)
        return fn
    return deco

def eligible(*, regime: str, style: str) -> list[StrategySpec]:
    out = []
    for spec in REGISTRY.values():
        if spec.intraday_only and style != "intraday":
            continue
        if regime not in spec.regimes:
            continue
        out.append(spec)
    return out
