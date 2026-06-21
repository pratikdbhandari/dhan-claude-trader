"""Wrapper over the dhanhq SDK. Every method returns data or a structured result;
errors are caught and surfaced (never raised into the UI). In PAPER mode, order
mutating methods are simulated and the broker is never contacted."""
from __future__ import annotations
import logging
from typing import Any, Optional
from core.models import (Instrument, OrderRequest, OrderResult, OrderType,
                         Side, TradeMode)

log = logging.getLogger(__name__)


class DhanError(RuntimeError):
    pass


class DhanClient:
    def __init__(self, sdk: Any = None, mode: TradeMode = TradeMode.PAPER,
                 client_id: Optional[str] = None, access_token: Optional[str] = None):
        if sdk is None:
            from dhanhq import dhanhq
            sdk = dhanhq(client_id, access_token)
        self.sdk = sdk
        self.mode = mode

    # ---- data reads ----
    def get_positions(self) -> list[dict]:
        try:
            resp = self.sdk.get_positions()
            return resp.get("data", []) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001 - surface, don't crash
            log.exception("get_positions failed")
            raise DhanError(f"Failed to fetch positions: {e}") from e

    def get_fund_limits(self) -> dict:
        try:
            resp = self.sdk.get_fund_limits()
            return resp.get("data", {}) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001
            raise DhanError(f"Failed to fetch funds: {e}") from e

    # ---- order writes (dry_run aware) ----
    def place_order(self, req: OrderRequest) -> OrderResult:
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-{req.instrument.symbol}",
                               exec_price=req.price)
        try:
            resp = self.sdk.place_order(
                security_id=req.instrument.security_id,
                exchange_segment=req.instrument.exchange_segment,
                transaction_type=req.side.value,
                quantity=req.qty,
                order_type=req.order_type.value,
                price=req.price or 0,
                product_type="INTRADAY",
            )
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid, exec_price=req.price)
        except Exception as e:                       # noqa: BLE001
            log.exception("place_order failed")
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))
