"""Defined-risk credit-spread builder. Direction comes from the consensus
(BUY -> bull-put, SELL -> bear-call); sell leg chosen by target delta, hedge leg
one strike further OTM. Returns a SpreadPlan with payoff metrics. Pure given a chain."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.models import SignalType
from services.options_chain import nearest_by_delta
from services.options_payoff import metrics


@dataclass
class SpreadPlan:
    name: str                      # bull_put | bear_call
    legs: list[dict] = field(default_factory=list)
    credit: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: list[float] = field(default_factory=list)
    sell_strike: float = 0.0
    buy_strike: float = 0.0


def build_credit_spread(consensus, chain: list[dict], spot: float, lot_size: int,
                        *, sell_delta: float = 0.30, lots: int = 1) -> SpreadPlan | None:
    if not chain or consensus.consensus is SignalType.HOLD:
        return None
    bullish = consensus.consensus is SignalType.BUY
    opt = "pe" if bullish else "ce"          # bull-put sells puts; bear-call sells calls
    name = "bull_put" if bullish else "bear_call"

    sell_row = nearest_by_delta(chain, opt, sell_delta)
    if sell_row is None:
        return None
    strikes = [r["strike"] for r in chain]
    idx = strikes.index(sell_row["strike"])
    # hedge is one strike further OTM: puts -> lower strike (idx-1); calls -> higher (idx+1)
    hedge_idx = idx - 1 if bullish else idx + 1
    if hedge_idx < 0 or hedge_idx >= len(chain):
        return None
    buy_row = chain[hedge_idx]

    sell_prem = sell_row[opt].get("ltp")
    buy_prem = buy_row[opt].get("ltp")
    if sell_prem is None or buy_prem is None:
        return None

    legs = [
        {"type": opt.upper(), "action": "SELL", "strike": sell_row["strike"],
         "premium": float(sell_prem), "lots": lots, "lot_size": lot_size},
        {"type": opt.upper(), "action": "BUY", "strike": buy_row["strike"],
         "premium": float(buy_prem), "lots": lots, "lot_size": lot_size},
    ]
    m = metrics(legs, spot_ref=spot)
    credit = round((float(sell_prem) - float(buy_prem)) * lots * lot_size, 2)
    return SpreadPlan(name=name, legs=legs, credit=credit,
                      max_profit=m["max_profit"], max_loss=m["max_loss"],
                      breakevens=m["breakevens"], sell_strike=sell_row["strike"],
                      buy_strike=buy_row["strike"])
