"""Pre-trade risk gate. Pure/injectable: takes equity, day P&L and open-position
count and decides if an order may proceed. Limits default to ₹10k daily loss,
1% risk per trade, 2 open positions (override via env; ask before changing)."""
from __future__ import annotations
import math
import os
from dataclasses import dataclass
from core.models import OrderRequest, RiskCheck, TradeMode


@dataclass
class RiskConfig:
    max_daily_loss: float = 10000.0
    max_risk_per_trade_pct: float = 1.0
    max_open_positions: int = 2


def load_risk_config(env: dict | None = None) -> RiskConfig:
    env = env if env is not None else os.environ
    return RiskConfig(
        max_daily_loss=float(env.get("MAX_DAILY_LOSS", 10000)),
        max_risk_per_trade_pct=float(env.get("MAX_RISK_PER_TRADE_PCT", 1.0)),
        max_open_positions=int(env.get("MAX_OPEN_POSITIONS", 2)),
    )


def position_size(equity: float, entry: float, stop_loss: float,
                  risk_pct: float) -> int:
    """Largest qty whose worst-case loss stays within risk_pct of equity."""
    per_share = abs(entry - stop_loss)
    if per_share == 0 or equity <= 0:
        return 0
    risk_amount = equity * risk_pct / 100.0
    return int(math.floor(risk_amount / per_share))


def day_pnl(mode: TradeMode, *, dhan_client=None, legs=None, ltp_fn=None) -> float:
    """LIVE: realized+unrealized from Dhan positions. PAPER: from accounting over
    journal legs (passed in)."""
    if mode is TradeMode.LIVE:
        positions = dhan_client.get_positions()
        total = 0.0
        for p in positions:
            total += float(p.get("realizedProfit", 0) or 0)
            total += float(p.get("unrealizedProfit", 0) or 0)
        return round(total, 2)
    # PAPER
    from services.accounting import pnl_statement
    stmt = pnl_statement(legs or [], mode="PAPER", period="all", period_key=None,
                         ltp_fn=ltp_fn or (lambda s: None))
    return stmt.total_pnl


def open_position_count(mode: TradeMode, *, dhan_client=None, legs=None) -> int:
    if mode is TradeMode.LIVE:
        return sum(1 for p in dhan_client.get_positions()
                   if int(p.get("netQty", 0) or 0) != 0)
    from services.accounting import portfolio
    return len(portfolio(legs or [], mode="PAPER", ltp_fn=lambda s: None))


def pre_trade_check(req: OrderRequest, cfg: RiskConfig, *, equity: float,
                    day_pnl_value: float, open_count: int) -> RiskCheck:
    reasons: list[str] = []
    if day_pnl_value <= -cfg.max_daily_loss:
        reasons.append(f"Daily loss limit reached (₹{day_pnl_value:.0f})")
    if open_count >= cfg.max_open_positions:
        reasons.append(f"Max open positions ({open_count}/{cfg.max_open_positions})")
    if req.stop_loss is not None and req.price is not None:
        trade_risk = req.qty * abs(req.price - req.stop_loss)
        if trade_risk > equity * cfg.max_risk_per_trade_pct / 100.0:
            reasons.append(
                f"Trade risk ₹{trade_risk:.0f} exceeds {cfg.max_risk_per_trade_pct}% "
                f"of equity (₹{equity * cfg.max_risk_per_trade_pct / 100:.0f})")
    if req.qty <= 0:
        reasons.append("Invalid quantity (0)")
    buffer = max(0.0, cfg.max_daily_loss + day_pnl_value)
    return RiskCheck(allowed=not reasons, reasons=reasons, day_pnl=day_pnl_value,
                     open_positions=open_count, remaining_loss_buffer=round(buffer, 2))
