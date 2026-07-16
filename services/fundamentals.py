"""yfinance fundamentals wrapper. ticker_factory injectable for tests.
Failures degrade to an empty dict."""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def _default_factory(symbol: str):
    import yfinance as yf
    sym = symbol if "." in symbol else f"{symbol}.NS"
    return yf.Ticker(sym)


def get_fundamentals(symbol: str, ticker_factory=None) -> dict:
    factory = ticker_factory or _default_factory
    try:
        info = getattr(factory(symbol), "info", {}) or {}
        pct = lambda v: round(v * 100, 2) if isinstance(v, (int, float)) else None  # noqa: E731
        return {
            "pe": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "market_cap": info.get("marketCap"),
            "earnings_date": info.get("earningsDate"),
            # shareholding (Yahoo: insiders ≈ promoter group for Indian listings)
            "promoter_pct": pct(info.get("heldPercentInsiders")),
            "institution_pct": pct(info.get("heldPercentInstitutions")),
        }
    except Exception as e:                     # noqa: BLE001
        log.warning("fundamentals failed for %s: %s", symbol, e)
        return {}
