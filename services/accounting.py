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
from core.models import Holding


def _open_lots(legs: list[dict], mode: str) -> dict[str, list[dict]]:
    """Replay FIFO and return remaining (unmatched) buy lots per symbol."""
    book = [l for l in legs if l["mode"] == mode and l["qty"] > 0]
    lots: dict[str, deque] = defaultdict(deque)
    for leg in book:
        sym = leg["symbol"]
        if leg["side"].upper() == "BUY":
            lots[sym].append({"qty": leg["qty"], "price": leg["price"],
                              "segment": leg["segment"]})
        else:
            sell_qty = leg["qty"]
            while sell_qty > 0 and lots[sym]:
                lot = lots[sym][0]
                matched = min(sell_qty, lot["qty"])
                lot["qty"] -= matched
                sell_qty -= matched
                if lot["qty"] == 0:
                    lots[sym].popleft()
    return {s: list(d) for s, d in lots.items() if d}


def portfolio(legs: list[dict], mode: str, ltp_fn) -> list[Holding]:
    out: list[Holding] = []
    for sym, lots in _open_lots(legs, mode).items():
        qty = sum(l["qty"] for l in lots)
        invested = round(sum(l["qty"] * l["price"] for l in lots), 2)
        avg_cost = round(invested / qty, 2) if qty else 0.0
        ltp = ltp_fn(sym)
        if ltp is None:
            cur = unreal = None
        else:
            cur = round(ltp * qty, 2)
            unreal = round((ltp - avg_cost) * qty, 2)
        out.append(Holding(symbol=sym, segment=lots[0]["segment"], mode=mode,
                           qty=qty, avg_cost=avg_cost, invested=invested,
                           ltp=ltp, current_value=cur, unrealized_pnl=unreal))
    return out
