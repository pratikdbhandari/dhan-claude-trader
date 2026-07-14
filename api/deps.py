"""FastAPI dependency providers — construct the same objects app.py wires up at
startup, so both presentation layers call identical service functions with
identical configuration."""
from __future__ import annotations
import json
from pathlib import Path

from core import config_store
from core.models import Instrument, TradeMode
from data.journal import init_db
from services import instruments, risk_manager
from services.dhan_client import DhanClient, DhanError

_journal_conn = None
_instrument_index: dict | None = None
_pending_store = None


def get_journal():
    global _journal_conn
    if _journal_conn is None:
        _journal_conn = init_db("trades.db")
    return _journal_conn


def get_dhan_client() -> DhanClient:
    mode = config_store.get_setting("TRADE_MODE", "PAPER")
    return DhanClient(client_id=config_store.get_setting("DHAN_CLIENT_ID"),
                      access_token=config_store.get_setting("DHAN_ACCESS_TOKEN"),
                      mode=TradeMode(mode))


def get_risk_config() -> risk_manager.RiskConfig:
    return risk_manager.load_risk_config({
        "MAX_DAILY_LOSS": config_store.get_setting("MAX_DAILY_LOSS", "10000"),
        "MAX_RISK_PER_TRADE_PCT": config_store.get_setting("MAX_RISK_PER_TRADE_PCT", "1.0"),
        "MAX_OPEN_POSITIONS": config_store.get_setting("MAX_OPEN_POSITIONS", "2"),
    })


def get_instrument_index() -> dict:
    global _instrument_index
    if _instrument_index is not None:
        return _instrument_index
    try:
        cache = instruments._CACHE
        text = (cache.read_text(encoding="utf-8") if cache.exists()
               else instruments.download_master())
        _instrument_index = instruments.build_index(text)
    except Exception:                                      # noqa: BLE001
        _instrument_index = {}
    return _instrument_index


def load_watchlist(path: str | Path = "watchlist.json") -> list[Instrument]:
    data = json.loads(Path(path).read_text())
    wl = [Instrument(symbol=i["symbol"], exchange_segment=i["exchange_segment"],
                     security_id=i.get("security_id"), lot_size=i.get("lot_size", 1),
                     kind=i.get("kind", "EQUITY"))
          for i in data["instruments"]]
    return instruments.resolve_watchlist(wl, get_instrument_index())


def get_equity(mode: str, dhan: DhanClient | None) -> float:
    if mode == "LIVE":
        try:
            funds = dhan.get_fund_limits()
            return float(funds.get("availabelBalance", funds.get("availableBalance", 0)) or 0)
        except DhanError:
            return 0.0
    return float(config_store.get_setting("ACCOUNT_CAPITAL", "100000"))


def get_pending_store():
    global _pending_store
    if _pending_store is None:
        from api.state import PendingStore
        ttl = int(config_store.get_setting("SIGNAL_COOLDOWN_SECONDS", "300"))
        _pending_store = PendingStore(ttl_seconds=ttl)
    return _pending_store
