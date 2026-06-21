"""Dhan option-chain wrapper: expiries, parsed chain (LTP/IV/Greeks/OI per strike),
and delta-based strike selection. Injectable SDK; tolerant parse; fail-safe."""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def get_expiries(instrument, dhan_client) -> list[str]:
    try:
        resp = dhan_client.sdk.expiry_list(
            int(instrument.security_id), instrument.exchange_segment)
        data = resp.get("data", resp) if isinstance(resp, dict) else resp
        return list(data) if data else []
    except Exception as e:                     # noqa: BLE001
        log.warning("expiry_list failed: %s", e)
        return []


def _leg(node: dict) -> dict:
    return {"ltp": node.get("last_price", node.get("ltp")),
            "iv": node.get("implied_volatility", node.get("iv")),
            "delta": (node.get("greeks") or {}).get("delta", node.get("delta")),
            "oi": node.get("oi", node.get("open_interest"))}


def get_chain(instrument, expiry: str, dhan_client) -> list[dict]:
    """Returns rows: {strike, ce:{ltp,iv,delta,oi}, pe:{...}}. Tolerant to shape."""
    try:
        resp = dhan_client.sdk.option_chain(
            int(instrument.security_id), instrument.exchange_segment, expiry)
        data = resp.get("data", resp) if isinstance(resp, dict) else resp
        oc = data.get("oc", data) if isinstance(data, dict) else {}
        rows = []
        for strike, node in (oc.items() if isinstance(oc, dict) else []):
            rows.append({"strike": float(strike),
                         "ce": _leg(node.get("ce", {})),
                         "pe": _leg(node.get("pe", {}))})
        return sorted(rows, key=lambda r: r["strike"])
    except Exception as e:                     # noqa: BLE001
        log.warning("option_chain failed: %s", e)
        return []


def nearest_by_delta(chain: list[dict], option: str, target_delta: float) -> dict | None:
    """Pick the strike whose option (ce/pe) delta is closest to target_delta.
    Falls back to None if no greeks present (caller can use %-OTM instead)."""
    key = option.lower()
    best, best_diff = None, 1e9
    for row in chain:
        d = row[key].get("delta")
        if d is None:
            continue
        diff = abs(abs(d) - abs(target_delta))
        if diff < best_diff:
            best, best_diff = row, diff
    return best
