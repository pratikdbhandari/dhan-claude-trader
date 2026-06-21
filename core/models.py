"""Typed domain models (DTOs) shared across all layers.

These are the contracts between services. Keeping them here means the UI,
signal engine, risk manager and journal all speak the same vocabulary and a
future REST refactor can serialize these directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class TradeMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    BRACKET = "BRACKET"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# --------------------------------------------------------------------------- #
# Instruments & market data
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange_segment: str
    security_id: Optional[str] = None
    lot_size: int = 1
    kind: str = "EQUITY"  # INDEX | EQUITY | OPTION


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
@dataclass
class ProviderSignal:
    """One provider's recommendation for one instrument."""
    provider: str
    signal: SignalType
    confidence: int           # 0-100
    entry: Optional[float]
    stop_loss: Optional[float]
    target: Optional[float]
    risk_reward_ratio: Optional[float]
    reasoning: str
    error: bool = False       # True => fell back to HOLD due to parse/API failure
    latency_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signal"] = self.signal.value
        return d


@dataclass
class ConsensusSignal:
    """Aggregate of all ProviderSignals for one instrument."""
    instrument: Instrument
    providers: list[ProviderSignal]
    consensus: SignalType
    avg_confidence: int
    agreement_pct: int        # % of providers agreeing with consensus
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    indicator_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> list[ProviderSignal]:
        return [p for p in self.providers if not p.error]


# --------------------------------------------------------------------------- #
# Orders & risk
# --------------------------------------------------------------------------- #
@dataclass
class OrderRequest:
    instrument: Instrument
    side: Side
    order_type: OrderType
    qty: int
    price: Optional[float] = None        # limit price
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    # provenance — what signal produced this (for the journal)
    source_signal: Optional[ConsensusSignal] = None


@dataclass
class RiskCheck:
    allowed: bool
    reasons: list[str] = field(default_factory=list)   # why blocked (if any)
    day_pnl: float = 0.0
    open_positions: int = 0
    remaining_loss_buffer: float = 0.0


@dataclass
class OrderResult:
    ok: bool
    mode: TradeMode
    dhan_order_id: Optional[str] = None
    status: str = ""           # PLACED | REJECTED | FILLED | ERROR
    exec_price: Optional[float] = None
    error_message: Optional[str] = None
