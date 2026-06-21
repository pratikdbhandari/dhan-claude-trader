"""Accounting over filled order legs. Pure: legs in, dataclasses out. FIFO lot
matching per (symbol, mode). Charges via services.charges."""
from __future__ import annotations
from collections import defaultdict, deque
from core.models import RealizedTrade
from services.charges import compute


def _charge_per_unit(leg: dict) -> float:
    c = compute(leg["segment"], leg["side"], leg["qty"], leg["price"], leg["mode"])
    return c.total / leg["qty"] if leg["qty"] else 0.0


def realized_trades(legs: list[dict], mode: str) -> list[RealizedTrade]:
    book = [l for l in legs if l["mode"] == mode and l["qty"] > 0]
    lots: dict[str, deque] = defaultdict(deque)
    out: list[RealizedTrade] = []

    for leg in book:
        sym = leg["symbol"]
        cpu = _charge_per_unit(leg)
        if leg["side"].upper() == "BUY":
            lots[sym].append({"qty": leg["qty"], "price": leg["price"],
                              "cpu": cpu, "ts": leg["timestamp"],
                              "rr": leg["rr_predicted"]})
            continue
        sell_qty = leg["qty"]
        while sell_qty > 0 and lots[sym]:
            lot = lots[sym][0]
            matched = min(sell_qty, lot["qty"])
            gross = round((leg["price"] - lot["price"]) * matched, 2)
            charges = round(matched * lot["cpu"] + matched * cpu, 2)
            out.append(RealizedTrade(
                symbol=sym, segment=leg["segment"], mode=mode, qty=matched,
                buy_price=lot["price"], sell_price=leg["price"],
                gross_pnl=gross, charges=charges, net_pnl=round(gross - charges, 2),
                rr_predicted=lot["rr"], rr_achieved=None,
                opened_at=lot["ts"], closed_at=leg["timestamp"]))
            lot["qty"] -= matched
            sell_qty -= matched
            if lot["qty"] == 0:
                lots[sym].popleft()
    return out
