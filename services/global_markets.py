"""World markets that move Indian shares — US, Europe, Asia, FX & commodities —
plus the direct/indirect linkage from each global driver to each stock's sector,
and NSE's daily FII/DII cash-market flows.

Data edges (yfinance, NSE) are TTL-cached and degrade to empty on failure; the
mapping core (which driver moves which stock, and why) is pure and testable.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ registry
# name -> (yahoo ticker, group)
WORLD: dict[str, tuple[str, str]] = {
    "S&P 500":        ("^GSPC", "US"),
    "NASDAQ":         ("^IXIC", "US"),
    "Dow Jones":      ("^DJI", "US"),
    "US 10Y yield":   ("^TNX", "US"),
    "FTSE 100":       ("^FTSE", "Europe"),
    "DAX":            ("^GDAXI", "Europe"),
    "Nikkei 225":     ("^N225", "Asia"),
    "Hang Seng":      ("^HSI", "Asia"),
    "Shanghai":       ("000001.SS", "Asia"),
    "KOSPI":          ("^KS11", "Asia"),
    "USD/INR":        ("INR=X", "FX & commodities"),
    "Dollar index":   ("DX-Y.NYB", "FX & commodities"),
    "Brent crude":    ("BZ=F", "FX & commodities"),
    "Gold":           ("GC=F", "FX & commodities"),
}
_BY_TICKER = {t: n for n, (t, _g) in WORLD.items()}

# ------------------------------------------------------------------ sectors
SECTOR: dict[str, str] = {
    "NIFTY": "INDEX", "BANKNIFTY": "BANKS", "FINNIFTY": "FINANCIALS",
    "MIDCPNIFTY": "INDEX", "SENSEX": "INDEX",
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT",
    "HDFCBANK": "BANKS", "ICICIBANK": "BANKS", "SBIN": "BANKS",
    "AXISBANK": "BANKS", "KOTAKBANK": "BANKS", "INDUSINDBK": "BANKS",
    "BAJFINANCE": "FINANCIALS", "BAJAJFINSV": "FINANCIALS", "JIOFIN": "FINANCIALS",
    "SHRIRAMFIN": "FINANCIALS", "SBILIFE": "FINANCIALS", "HDFCLIFE": "FINANCIALS",
    "RELIANCE": "OIL_GAS", "ONGC": "OIL_UPSTREAM", "BPCL": "OIL_REFINING",
    "TATASTEEL": "METALS", "HINDALCO": "METALS", "JSWSTEEL": "METALS",
    "COALINDIA": "METALS",
    "MARUTI": "AUTO", "M&M": "AUTO", "EICHERMOT": "AUTO",
    "HEROMOTOCO": "AUTO", "BAJAJ-AUTO": "AUTO",
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA", "CIPLA": "PHARMA",
    "APOLLOHOSP": "PHARMA",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TATACONSUM": "FMCG", "ASIANPAINT": "FMCG",
    "TITAN": "CONSUMER", "TRENT": "CONSUMER",
    "LT": "INFRA", "ULTRACEMCO": "INFRA", "GRASIM": "INFRA",
    "POWERGRID": "UTILITIES", "NTPC": "UTILITIES",
    "ADANIENT": "INFRA", "ADANIPORTS": "INFRA", "BHARTIARTL": "TELECOM",
}

# sector -> [(yahoo ticker, sign, why)]; sign +1 = driver up helps the stock,
# -1 = driver up hurts it. This is the direct/indirect world→India linkage.
DRIVERS: dict[str, list[tuple[str, int, str]]] = {
    "IT": [("^IXIC", +1, "US tech spending drives Indian IT order books"),
           ("^GSPC", +1, "US corporate health = IT budgets"),
           ("INR=X", +1, "weaker rupee (USD/INR up) lifts export margins")],
    "BANKS": [("^TNX", -1, "rising US yields pull FII money out of EM banks"),
              ("DX-Y.NYB", -1, "strong dollar = FII outflows from India"),
              ("^GSPC", +1, "global risk appetite lifts financials")],
    "FINANCIALS": [("^TNX", -1, "US yields compete for the same FII flows"),
                   ("DX-Y.NYB", -1, "dollar strength = EM outflows"),
                   ("^GSPC", +1, "risk-on supports lenders/insurers")],
    "OIL_GAS": [("BZ=F", +1, "GRM & upstream realisations track Brent"),
                ("DX-Y.NYB", -1, "crude priced in dollars")],
    "OIL_UPSTREAM": [("BZ=F", +1, "crude price = realisation per barrel")],
    "OIL_REFINING": [("BZ=F", -1, "crude is the input cost; marketing margins shrink")],
    "METALS": [("000001.SS", +1, "China demand sets global metal prices"),
               ("^HSI", +1, "China sentiment proxy"),
               ("DX-Y.NYB", -1, "dollar-priced commodities fall when USD rises")],
    "AUTO": [("BZ=F", -1, "fuel prices dent vehicle demand"),
             ("^GSPC", +1, "global growth sentiment"),
             ("^N225", +1, "Japan parents/partners (Suzuki, tech tie-ups)")],
    "PHARMA": [("INR=X", +1, "US generics revenue is in dollars"),
               ("^GSPC", +1, "US healthcare spending environment")],
    "FMCG": [("BZ=F", -1, "crude-linked packaging & input costs"),
             ("GC=F", 0, "defensive — moves with risk-off, weak linkage")],
    "CONSUMER": [("GC=F", +1, "gold demand (jewellery) tracks gold prices"),
                 ("^GSPC", +1, "discretionary spending sentiment")],
    "INFRA": [("^TNX", -1, "rate-sensitive capex financing"),
              ("000001.SS", +1, "China = commodity/capex cycle proxy")],
    "UTILITIES": [("^TNX", -1, "bond-proxy sector, hurt by rising yields")],
    "TELECOM": [("^GSPC", +1, "risk sentiment; capex funding costs")],
    "INDEX": [("^GSPC", +1, "Wall Street sets the overnight gap"),
              ("^N225", +1, "Asian session sentiment"),
              ("^HSI", +1, "Asia risk appetite"),
              ("DX-Y.NYB", -1, "strong dollar = FII selling"),
              ("BZ=F", -1, "India imports ~85% of its crude"),
              ("^TNX", -1, "US yields compete for FII flows")],
}

_cache: dict = {"ts": 0.0, "rows": {}}
_flows_cache: dict = {"ts": 0.0, "flows": []}
_lock = threading.Lock()


# ------------------------------------------------------------------ snapshot
def _fetch_world() -> dict[str, dict]:
    import yfinance as yf
    tickers = [t for t, _g in WORLD.values()]
    df = yf.download(" ".join(tickers), period="5d", interval="1d",
                     group_by="ticker", threads=True, progress=False)
    rows: dict[str, dict] = {}
    for name, (ticker, group) in WORLD.items():
        try:
            closes = df[ticker]["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            rows[ticker] = {"name": name, "ticker": ticker, "group": group,
                            "last": round(last, 2),
                            "pct": round((last - prev) / prev * 100, 2)}
        except Exception:                          # noqa: BLE001
            continue
    return rows


def snapshot(ttl: float = 600.0, fetch=None) -> dict[str, dict]:
    """{yahoo_ticker: row} for the world registry; cached, degrades to last/empty."""
    now = time.monotonic()
    with _lock:
        if (now - _cache["ts"]) < ttl and _cache["rows"]:
            return _cache["rows"]
    try:
        rows = (fetch or _fetch_world)()
    except Exception:                              # noqa: BLE001
        log.warning("world snapshot failed", exc_info=True)
        rows = {}
    with _lock:
        if rows:
            _cache.update(ts=now, rows=rows)
        return _cache["rows"]


def risk_sentiment(rows: dict[str, dict]) -> dict:
    """RISK-ON / RISK-OFF / MIXED from the major equity benchmarks."""
    majors = ["^GSPC", "^IXIC", "^N225", "^HSI", "^FTSE"]
    pcts = [rows[t]["pct"] for t in majors if t in rows]
    if not pcts:
        return {"label": "UNKNOWN", "avg": None}
    avg = round(sum(pcts) / len(pcts), 2)
    up = sum(1 for p in pcts if p > 0.15)
    down = sum(1 for p in pcts if p < -0.15)
    label = ("RISK-ON" if up >= 3 and avg > 0
             else "RISK-OFF" if down >= 3 and avg < 0 else "MIXED")
    return {"label": label, "avg": avg}


def grouped(rows: dict[str, dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for name, (ticker, group) in WORLD.items():
        if ticker in rows:
            out.setdefault(group, []).append(rows[ticker])
    return out


# ------------------------------------------------------------------ per-stock
def stock_drivers(symbol: str, rows: dict[str, dict]) -> dict:
    """Which world markets move THIS share, live moves attached, and the net cue.

    aligned = sign * pct: positive means that driver's move currently supports
    the stock, negative means it currently works against it."""
    sector = SECTOR.get(symbol.upper(), "INDEX")
    out = []
    score = 0.0
    for ticker, sign, why in DRIVERS.get(sector, DRIVERS["INDEX"]):
        row = rows.get(ticker)
        entry = {"name": _BY_TICKER.get(ticker, ticker), "ticker": ticker,
                 "sign": sign, "why": why, "pct": None, "aligned": None}
        if row is not None and sign != 0:
            entry["pct"] = row["pct"]
            entry["aligned"] = round(sign * row["pct"], 2)
            score += entry["aligned"]
        elif row is not None:
            entry["pct"] = row["pct"]
        out.append(entry)
    n = sum(1 for e in out if e["aligned"] is not None)
    avg = round(score / n, 2) if n else None
    cue = ("UNKNOWN" if avg is None
           else "SUPPORTIVE" if avg > 0.25
           else "AGAINST" if avg < -0.25 else "NEUTRAL")
    return {"sector": sector, "drivers": out, "score": avg, "cue": cue}


# ------------------------------------------------------------------ FII/DII
def _fetch_fii_dii() -> list[dict]:
    import requests
    h = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/126 Safari/537.36"),
         "Accept-Language": "en-US,en;q=0.9",
         "Referer": "https://www.nseindia.com/"}
    s = requests.Session()
    s.get("https://www.nseindia.com", headers=h, timeout=8)
    r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", headers=h, timeout=8)
    r.raise_for_status()
    out = []
    for row in r.json():
        try:
            out.append({"category": row["category"], "date": row["date"],
                        "buy": float(row["buyValue"]), "sell": float(row["sellValue"]),
                        "net": float(row["netValue"])})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def fii_dii(ttl: float = 1800.0, fetch=None) -> list[dict]:
    """NSE daily cash-market FII/FPI + DII flows (₹ crore). Unofficial endpoint —
    cached hard and degrades to the last good copy (or empty)."""
    now = time.monotonic()
    with _lock:
        if (now - _flows_cache["ts"]) < ttl and _flows_cache["flows"]:
            return _flows_cache["flows"]
    try:
        flows = (fetch or _fetch_fii_dii)()
    except Exception:                              # noqa: BLE001
        log.warning("NSE fii/dii fetch failed", exc_info=True)
        flows = []
    with _lock:
        if flows:
            _flows_cache.update(ts=now, flows=flows)
        return _flows_cache["flows"]
