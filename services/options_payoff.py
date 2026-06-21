"""Pure options payoff math at expiry. A leg is a dict:
{type: 'CE'|'PE', action: 'BUY'|'SELL', strike, premium, lots, lot_size}.
Returns payoff curve + max profit/loss/breakevens. No data, fully testable."""
from __future__ import annotations


def _leg_payoff(leg: dict, spot: float) -> float:
    qty = leg["lots"] * leg["lot_size"]
    strike, prem = leg["strike"], leg["premium"]
    if leg["type"].upper() == "CE":
        intrinsic = max(spot - strike, 0.0)
    else:  # PE
        intrinsic = max(strike - spot, 0.0)
    if leg["action"].upper() == "BUY":
        return (intrinsic - prem) * qty
    return (prem - intrinsic) * qty            # SELL


def payoff_curve(legs: list[dict], spot_min: float, spot_max: float,
                 step: float | None = None) -> tuple[list[float], list[float]]:
    step = step or max(1.0, (spot_max - spot_min) / 100)
    xs, ys = [], []
    s = spot_min
    while s <= spot_max:
        xs.append(round(s, 2))
        ys.append(round(sum(_leg_payoff(l, s) for l in legs), 2))
        s += step
    return xs, ys


def metrics(legs: list[dict], spot_ref: float) -> dict:
    """max profit/loss over a wide spot range + breakevens (sign changes)."""
    lo, hi = spot_ref * 0.7, spot_ref * 1.3
    xs, ys = payoff_curve(legs, lo, hi, step=(hi - lo) / 400)
    max_profit = round(max(ys), 2)
    max_loss = round(min(ys), 2)
    breakevens = []
    for i in range(1, len(ys)):
        if (ys[i - 1] <= 0 < ys[i]) or (ys[i - 1] >= 0 > ys[i]):
            breakevens.append(round((xs[i - 1] + xs[i]) / 2, 2))
    return {"max_profit": max_profit, "max_loss": max_loss,
            "breakevens": breakevens}
