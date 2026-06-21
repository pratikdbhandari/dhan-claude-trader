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


def _walk_for_price(obj):
    """Depth-first search for the first last_price/ltp value in a nested dict/list."""
    if isinstance(obj, dict):
        for key in ("last_price", "ltp", "LTP"):
            if key in obj and isinstance(obj[key], (int, float)):
                return obj[key]
        for v in obj.values():
            found = _walk_for_price(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _walk_for_price(v)
            if found is not None:
                return found
    return None


def _candles_to_df(resp):
    import pandas as pd
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    cols = ["open", "high", "low", "close", "volume"]
    if not all(k in data for k in cols):
        return pd.DataFrame(columns=cols)
    frame = {k: data[k] for k in cols}
    if "timestamp" in data:
        frame["timestamp"] = data["timestamp"]
    return pd.DataFrame(frame)


class DhanClient:
    _INSTRUMENT_TYPE = {"EQUITY": "EQUITY", "INDEX": "INDEX",
                        "FUT": "FUTIDX", "OPT": "OPTIDX"}

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

    def get_ltp(self, instrument) -> float:
        try:
            resp = self.sdk.ticker_data(
                {instrument.exchange_segment: [int(instrument.security_id)]})
            price = _walk_for_price(resp)
            if price is None:
                raise DhanError("LTP not found in ticker response")
            return float(price)
        except DhanError:
            raise
        except Exception as e:                       # noqa: BLE001
            log.exception("get_ltp failed")
            raise DhanError(f"Failed to fetch LTP: {e}") from e

    def get_candles(self, instrument, interval, lookback_days: int = 5):
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        itype = self._INSTRUMENT_TYPE.get(instrument.kind.upper(), "EQUITY")
        try:
            if interval == "day":
                resp = self.sdk.historical_daily_data(
                    instrument.security_id, instrument.exchange_segment, itype,
                    from_date, to_date)
            else:
                resp = self.sdk.intraday_minute_data(
                    instrument.security_id, instrument.exchange_segment, itype,
                    from_date, to_date, interval=int(interval))
            return _candles_to_df(resp)
        except Exception as e:                       # noqa: BLE001
            log.exception("get_candles failed")
            raise DhanError(f"Failed to fetch candles: {e}") from e

    def get_holdings(self) -> list:
        try:
            resp = self.sdk.get_holdings()
            return resp.get("data", []) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001
            raise DhanError(f"Failed to fetch holdings: {e}") from e

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

    def modify_order(self, order_id: str, **changes):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="MODIFIED",
                               dhan_order_id=order_id)
        try:
            self.sdk.modify_order(order_id=order_id, **changes)
            return OrderResult(ok=True, mode=TradeMode.LIVE, status="MODIFIED",
                               dhan_order_id=order_id)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def cancel_order(self, order_id: str):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="CANCELLED",
                               dhan_order_id=order_id)
        try:
            self.sdk.cancel_order(order_id)
            return OrderResult(ok=True, mode=TradeMode.LIVE, status="CANCELLED",
                               dhan_order_id=order_id)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def exit_position(self, instrument):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-EXIT-{instrument.symbol}")
        try:
            positions = self.get_positions()
            net = 0
            for p in positions:
                if str(p.get("securityId")) == str(instrument.security_id):
                    net = int(p.get("netQty", 0))
                    break
            if net == 0:
                return OrderResult(ok=True, mode=TradeMode.LIVE, status="FLAT")
            side = "SELL" if net > 0 else "BUY"
            resp = self.sdk.place_order(
                security_id=instrument.security_id,
                exchange_segment=instrument.exchange_segment,
                transaction_type=side, quantity=abs(net),
                order_type="MARKET", product_type="INTRADAY", price=0)
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid)
        except Exception as e:                       # noqa: BLE001
            log.exception("exit_position failed")
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))

    def place_bracket_order(self, req):
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-BO-{req.instrument.symbol}",
                               exec_price=req.price)
        try:
            entry = req.price or 0
            profit = round(abs((req.target or entry) - entry), 2)
            stop = round(abs(entry - (req.stop_loss or entry)), 2)
            resp = self.sdk.place_order(
                security_id=req.instrument.security_id,
                exchange_segment=req.instrument.exchange_segment,
                transaction_type=req.side.value, quantity=req.qty,
                order_type=req.order_type.value, product_type="BO", price=entry,
                bo_profit_value=profit, bo_stop_loss_Value=stop)
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid, exec_price=entry)
        except Exception as e:                       # noqa: BLE001
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))
