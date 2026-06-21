"""Centralised configuration — single source of truth, fail-loud.

Loads .env, providers.json and watchlist.json. Missing-but-required values
raise ConfigError with a clear message instead of letting the app crash
cryptically deep inside a service call.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from core.models import Instrument, TradeMode

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Raised for missing/invalid configuration. Surfaced to the UI."""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    label: str
    kind: str          # 'anthropic' | 'openai'
    model: str
    base_url: Optional[str]
    key_env: str
    enabled: bool

    def api_key(self) -> Optional[str]:
        val = os.getenv(self.key_env, "").strip()
        return val or None

    @property
    def usable(self) -> bool:
        """Enabled AND has a key present."""
        return self.enabled and bool(self.api_key())


@dataclass(frozen=True)
class AppConfig:
    dhan_client_id: Optional[str]
    dhan_access_token: Optional[str]
    signal_source: str               # 'mock' | 'ai'
    trade_mode: TradeMode
    max_daily_loss: float
    max_risk_per_trade_pct: float
    max_open_positions: int
    signal_cooldown_seconds: int
    providers: list[ProviderConfig] = field(default_factory=list)
    instruments: list[Instrument] = field(default_factory=list)

    # ---- validation helpers (called by the UI, not at import) ----
    def require_dhan(self) -> None:
        missing = [n for n, v in
                   (("DHAN_CLIENT_ID", self.dhan_client_id),
                    ("DHAN_ACCESS_TOKEN", self.dhan_access_token)) if not v]
        if missing:
            raise ConfigError(
                "Missing Dhan credentials in .env: " + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )

    @property
    def usable_providers(self) -> list[ProviderConfig]:
        return [p for p in self.providers if p.usable]

    def require_ai(self) -> None:
        if self.signal_source == "ai" and not self.usable_providers:
            raise ConfigError(
                "SIGNAL_SOURCE=ai but no provider is both enabled and has an "
                "API key set. Enable a provider in providers.json and add its "
                "key to .env, or set SIGNAL_SOURCE=mock."
            )


def _load_providers() -> list[ProviderConfig]:
    path = ROOT / "providers.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[ProviderConfig] = []
    for p in data.get("providers", []):
        out.append(ProviderConfig(
            name=p["name"], label=p.get("label", p["name"]),
            kind=p["kind"], model=p["model"],
            base_url=p.get("base_url"), key_env=p["key_env"],
            enabled=bool(p.get("enabled", False)),
        ))
    return out


def _load_instruments() -> list[Instrument]:
    path = ROOT / "watchlist.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Instrument(
            symbol=i["symbol"], exchange_segment=i["exchange_segment"],
            security_id=i.get("security_id"), lot_size=int(i.get("lot_size", 1)),
            kind=i.get("kind", "EQUITY"),
        )
        for i in data.get("instruments", [])
    ]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def load_config() -> AppConfig:
    load_dotenv(ROOT / ".env")
    mode_raw = os.getenv("TRADE_MODE", "PAPER").upper()
    trade_mode = TradeMode.LIVE if mode_raw == "LIVE" else TradeMode.PAPER
    return AppConfig(
        dhan_client_id=os.getenv("DHAN_CLIENT_ID", "").strip() or None,
        dhan_access_token=os.getenv("DHAN_ACCESS_TOKEN", "").strip() or None,
        signal_source=os.getenv("SIGNAL_SOURCE", "mock").strip().lower(),
        trade_mode=trade_mode,
        max_daily_loss=_env_float("MAX_DAILY_LOSS", 10000.0),
        max_risk_per_trade_pct=_env_float("MAX_RISK_PER_TRADE_PCT", 1.0),
        max_open_positions=_env_int("MAX_OPEN_POSITIONS", 2),
        signal_cooldown_seconds=_env_int("SIGNAL_COOLDOWN_SECONDS", 300),
        providers=_load_providers(),
        instruments=_load_instruments(),
    )
