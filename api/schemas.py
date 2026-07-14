"""Pydantic request/response models for the API layer. These mirror core/models.py
dataclasses for JSON serialization; core/models.py itself is unchanged."""
from __future__ import annotations
from typing import Optional

from pydantic import BaseModel


class RiskCheckOut(BaseModel):
    allowed: bool
    reasons: list[str]
    day_pnl: float
    open_positions: int
    remaining_loss_buffer: float


class PendingSignalOut(BaseModel):
    pending_id: str
    symbol: str
    side: str
    qty: int
    entry: Optional[float]
    stop_loss: Optional[float]
    target: Optional[float]
    consensus: str
    avg_confidence: int
    agreement_pct: int
    risk_check: RiskCheckOut


class ConfirmResponse(BaseModel):
    ok: bool
    status: str
    dhan_order_id: Optional[str] = None
    exec_price: Optional[float] = None
    error_message: Optional[str] = None


class RiskSettingsOut(BaseModel):
    max_daily_loss: float
    max_risk_per_trade_pct: float
    max_open_positions: int


class RiskSettingsIn(BaseModel):
    max_daily_loss: Optional[float] = None
    max_risk_per_trade_pct: Optional[float] = None
    max_open_positions: Optional[int] = None


class GateOut(BaseModel):
    id: str
    label: str
    kind: str
    passed: bool


class ReadinessOut(BaseModel):
    gates: list[GateOut]
    passed_count: int
    all_passed: bool


class PushTokenIn(BaseModel):
    token: str


class OptionLegIn(BaseModel):
    type: str            # "CE" | "PE"
    action: str          # "BUY" | "SELL"
    strike: float
    premium: float
    lots: int
    lot_size: int


class PayoffRequest(BaseModel):
    legs: list[OptionLegIn]
    spot_ref: float


class PayoffOut(BaseModel):
    xs: list[float]
    ys: list[float]
    max_profit: float
    max_loss: float
    breakevens: list[float]
