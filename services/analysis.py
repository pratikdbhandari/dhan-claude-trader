"""Full structured trade analysis for one instrument.

Fuses everything the app already computes — strategy confluence votes, the
consensus signal, the tri-factor quality gate, indicator readings, RSS news
classified positive/negative for the specific share, and fundamentals — into
one dict the analysis page renders. Pure core (analyze_frame) + cached
network edges (news/fundamentals). Failures degrade per-section, never raise.

Honest framing: the verdict is 'setup quality', not a profit guarantee.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from core.models import SignalType
from services import indicators as ind
from services import signal_engine
from services.quality_gate import apply_gate
from services.strategies.engine import build_confluence
import services.strategies.trend            # noqa: F401 - register strategies
import services.strategies.mean_reversion   # noqa: F401
import services.strategies.breakout         # noqa: F401
import services.strategies.volume           # noqa: F401
import services.strategies.structure        # noqa: F401

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ news layer
# Which headline mentions THIS share? Alias keywords per symbol (lowercase).
ALIASES: dict[str, list[str]] = {
    "NIFTY": ["nifty", "sensex", "d-street", "dalal street"],
    "BANKNIFTY": ["bank nifty", "banknifty", "banking stocks"],
    "FINNIFTY": ["fin nifty", "financial services"],
    "MIDCPNIFTY": ["midcap"],
    "SENSEX": ["sensex", "nifty", "d-street", "dalal street"],
    "RELIANCE": ["reliance", "ril", "ambani"],
    "HDFCBANK": ["hdfc bank"],
    "TCS": ["tcs", "tata consultancy"],
    "INFY": ["infosys"],
    "ICICIBANK": ["icici bank"],
    "SBIN": ["sbi", "state bank"],
    "ITC": ["itc"],
    "LT": ["l&t", "larsen"],
    "AXISBANK": ["axis bank"],
    "KOTAKBANK": ["kotak"],
    "BHARTIARTL": ["airtel", "bharti"],
    "HINDUNILVR": ["hindustan unilever", "hul"],
    "BAJFINANCE": ["bajaj finance"],
    "MARUTI": ["maruti"],
    "ASIANPAINT": ["asian paints"],
    "TITAN": ["titan"],
    "SUNPHARMA": ["sun pharma"],
    "WIPRO": ["wipro"],
    "NTPC": ["ntpc"],
    "POWERGRID": ["power grid"],
    "ULTRACEMCO": ["ultratech"],
    "TATASTEEL": ["tata steel"],
    "ADANIENT": ["adani enterprises", "adani group"],
    "ADANIPORTS": ["adani ports"],
    "HCLTECH": ["hcl tech", "hcltech"],
    "TECHM": ["tech mahindra"],
    "M&M": ["mahindra & mahindra", "m&m"],
    "ONGC": ["ongc"],
    "JSWSTEEL": ["jsw steel"],
    "COALINDIA": ["coal india"],
    "BAJAJFINSV": ["bajaj finserv"],
    "DRREDDY": ["dr reddy", "dr. reddy"],
    "GRASIM": ["grasim"],
    "CIPLA": ["cipla"],
    "EICHERMOT": ["eicher", "royal enfield"],
    "HEROMOTOCO": ["hero moto"],
    "NESTLEIND": ["nestle"],
    "INDUSINDBK": ["indusind"],
    "APOLLOHOSP": ["apollo hospital"],
    "BRITANNIA": ["britannia"],
    "TATACONSUM": ["tata consumer"],
    "HINDALCO": ["hindalco"],
    "BPCL": ["bpcl", "bharat petroleum"],
    "SHRIRAMFIN": ["shriram finance"],
    "BAJAJ-AUTO": ["bajaj auto"],
    "SBILIFE": ["sbi life"],
    "HDFCLIFE": ["hdfc life"],
    "TRENT": ["trent", "zudio"],
    "JIOFIN": ["jio financial"],
}

_POSITIVE = ("surge", "soar", "jump", "rally", "rallies", "gain", "rise", "rises",
             "record high", "beats", "beat estimates", "strong", "profit up",
             "profit rises", "profit jumps", "upgrade", "buy rating", "wins",
             "bags", "order win", "expansion", "dividend", "bonus", "growth",
             "boost", "approval", "approves", "launch", "higher", "outperform",
             "upbeat", "top pick", "breakout", "all-time high")
_NEGATIVE = ("fall", "falls", "drop", "drops", "slump", "plunge", "plunges",
             "decline", "loss", "losses", "weak", "miss", "misses", "downgrade",
             "sell rating", "probe", "penalty", "fraud", "scam", "strike",
             "recall", "cuts", "cut guidance", "lower", "concern", "warning",
             "lawsuit", "ban", "resign", "crash", "sink", "sinks", "tumble",
             "underperform", "pressure", "layoff", "default", "downtrend")


# Corporate-event buckets: orders, results, management, pledges, promoter/FII
# holding changes, regulatory, corporate actions — detected from headlines.
EVENT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "ORDERS": ("order", "contract", "bags", "wins deal", "wins order", "loi",
               "letter of intent", "tender"),
    "RESULTS": ("result", "earnings", "quarterly", "profit", "revenue", "ebitda",
                "net loss", "q1", "q2", "q3", "q4"),
    "MANAGEMENT": ("ceo", "cfo", "managing director", "chairman", "resigns",
                   "resignation", "appoints", "appointed", "steps down",
                   "new md", "board of directors"),
    "PLEDGE": ("pledge", "pledged shares", "revoke pledge", "unpledge"),
    "HOLDING CHANGE": ("stake", "promoter", "shareholding", "fii holding",
                       "dii holding", "block deal", "bulk deal", "buyback",
                       "open offer", "raises holding", "cuts stake", "divest"),
    "REGULATORY": ("sebi", "penalty", "probe", "investigation", "tax notice",
                   "show cause", "cci", "ed ", "enforcement directorate"),
    "CORP ACTION": ("dividend", "bonus issue", "stock split", "rights issue",
                    "demerger", "merger", "acquisition", "amalgamation"),
}


def classify_corporate_events(symbol: str, headlines: list[str]) -> list[dict]:
    """Stock-specific headlines bucketed into corporate-event categories, each
    with its sentiment. One headline can carry multiple categories."""
    aliases = ALIASES.get(symbol.upper(), [symbol.lower()])
    events: list[dict] = []
    for h in headlines:
        low = h.lower()
        if not any(a in low for a in aliases):
            continue
        cats = [cat for cat, keys in EVENT_CATEGORIES.items()
                if any(k in low for k in keys)]
        if cats:
            events.append({"title": h, "categories": cats,
                           "sentiment": headline_sentiment(h)})
    return events


def headline_sentiment(title: str) -> str:
    """Keyword-count sentiment for one headline: POSITIVE | NEGATIVE | NEUTRAL."""
    t = title.lower()
    pos = sum(1 for k in _POSITIVE if k in t)
    neg = sum(1 for k in _NEGATIVE if k in t)
    if pos > neg:
        return "POSITIVE"
    if neg > pos:
        return "NEGATIVE"
    return "NEUTRAL"


def classify_news(symbol: str, headlines: list[str]) -> dict:
    """Split headlines into stock-specific pos/neg/neutral + general market ones
    (market headlines keep their sentiment tag for context)."""
    aliases = ALIASES.get(symbol.upper(), [symbol.lower()])
    stock = {"POSITIVE": [], "NEGATIVE": [], "NEUTRAL": []}
    market: list[dict] = []
    for h in headlines:
        low = h.lower()
        tag = headline_sentiment(h)
        if any(a in low for a in aliases):
            stock[tag].append(h)
        else:
            market.append({"title": h, "sentiment": tag})
    net = len(stock["POSITIVE"]) - len(stock["NEGATIVE"])
    return {"positive": stock["POSITIVE"], "negative": stock["NEGATIVE"],
            "neutral": stock["NEUTRAL"],
            "net": "POSITIVE" if net > 0 else "NEGATIVE" if net < 0 else "NEUTRAL",
            "market": market[:8]}


# TTL caches so the analysis page never hammers RSS / yfinance.
_news_cache: dict = {"ts": 0.0, "headlines": []}
_fund_cache: dict[str, tuple[float, dict]] = {}
_net_lock = threading.Lock()


def cached_headlines(ttl: float = 300.0, fetch=None) -> list[str]:
    from services import news as news_mod
    now = time.monotonic()
    with _net_lock:
        if (now - _news_cache["ts"]) < ttl and _news_cache["headlines"]:
            return _news_cache["headlines"]
    try:
        heads = news_mod.get_headlines("MARKET", fetch=fetch)
    except Exception:                              # noqa: BLE001
        log.warning("news fetch failed", exc_info=True)
        heads = []
    with _net_lock:
        if heads:
            _news_cache.update(ts=now, headlines=heads)
        return _news_cache["headlines"]


def cached_fundamentals(symbol: str, kind: str, ttl: float = 1800.0) -> dict:
    if kind.upper() != "EQUITY":
        return {}
    from services.fundamentals import get_fundamentals
    now = time.monotonic()
    with _net_lock:
        hit = _fund_cache.get(symbol)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]
    f = get_fundamentals(symbol)
    with _net_lock:
        _fund_cache[symbol] = (now, f)
    return f


# ------------------------------------------------------------------ core
def _fmt(x, nd=2):
    return round(float(x), nd) if x is not None else None


def _indicator_readings(df) -> dict:
    out: dict = {k: None for k in ("rsi", "atr", "ema20", "ema50",
                                   "macd_hist", "bb_pos", "adx")}
    try:
        close = df["close"]
        r = ind.rsi(close).dropna()
        out["rsi"] = _fmt(r.iloc[-1], 1) if len(r) else None
        out["atr"] = _fmt(ind.atr(df).dropna().iloc[-1])
        out["ema20"] = _fmt(ind.ema(close, 20).iloc[-1])
        out["ema50"] = _fmt(ind.ema(close, 50).iloc[-1])
        macd, sig, hist = ind.macd_lines(close)
        out["macd_hist"] = _fmt(hist.dropna().iloc[-1], 3) if len(hist.dropna()) else None
        lo, mid, up = ind.bollinger(close)
        out["bb_pos"] = _fmt((close.iloc[-1] - lo.iloc[-1])
                             / ((up.iloc[-1] - lo.iloc[-1]) or 1), 2)
        a = ind.adx(df).dropna()
        out["adx"] = _fmt(a.iloc[-1], 1) if len(a) else None
    except Exception:                              # noqa: BLE001
        log.warning("indicator readings failed", exc_info=True)
    return out


def _pros_cons(side: SignalType, snap, gate, news: dict, readings: dict,
               cs) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    supporting = [v for v in snap.votes if v.vote is side and side is not SignalType.HOLD]
    opposing = [v for v in snap.votes
                if v.vote not in (side, SignalType.HOLD)]
    for v in sorted(supporting, key=lambda v: -v.strength)[:5]:
        pros.append(f"{v.name} ({v.category}, strength {v.strength}): "
                    f"{v.detail or v.vote.value}")
    for v in sorted(opposing, key=lambda v: -v.strength)[:5]:
        cons.append(f"{v.name} ({v.category}, strength {v.strength}) votes "
                    f"{v.vote.value}: {v.detail or 'against the setup'}")

    if gate.passed:
        pros.append(f"Quality gate PASS — score {gate.score}/100")
    elif gate.vetoed:
        cons.append(f"Quality gate VETO — {'; '.join(gate.cautions) or 'hard block'}")
    else:
        cons.append(f"Quality score {gate.score} below threshold 50")
    for c in gate.cautions:
        if c not in " ".join(cons):
            cons.append(c)

    if cs.agreement_pct >= 75 and side is not SignalType.HOLD:
        pros.append(f"Provider agreement {cs.agreement_pct}%")
    if cs.avg_confidence < 40 and side is not SignalType.HOLD:
        cons.append(f"Low signal confidence ({cs.avg_confidence}%)")

    rsi = readings.get("rsi")
    if rsi is not None:
        if side is SignalType.BUY and rsi > 70:
            cons.append(f"RSI {rsi} overbought — late entry risk on a long")
        elif side is SignalType.SELL and rsi < 30:
            cons.append(f"RSI {rsi} oversold — bounce risk on a short")
        elif 40 <= rsi <= 60:
            pros.append(f"RSI {rsi} neutral — room to move")

    if snap.regime.value == "VOLATILE":
        cons.append("VOLATILE regime — wider stops, whipsaw risk")
    elif snap.regime.value == "TRENDING" and side is not SignalType.HOLD:
        pros.append("TRENDING regime favours directional trades")

    if side is SignalType.BUY and news["net"] == "NEGATIVE":
        cons.append(f"Net-negative news flow ({len(news['negative'])} negative "
                    f"vs {len(news['positive'])} positive headlines)")
    elif side is SignalType.SELL and news["net"] == "POSITIVE":
        cons.append(f"Net-positive news flow ({len(news['positive'])} positive "
                    f"headlines) argues against a short")
    elif news["net"] != "NEUTRAL":
        pros.append(f"News flow {news['net'].lower()} supports the direction")
    return pros, cons


def _global_pros_cons(side: SignalType, glob: Optional[dict],
                      pros: list[str], cons: list[str]) -> None:
    """Fold the world-market cue into the reasons: a supportive global backdrop
    is a pro for longs / con for shorts, and vice versa."""
    if not glob or glob.get("cue") in (None, "UNKNOWN") or side is SignalType.HOLD:
        return
    moved = [d for d in glob["drivers"]
             if d.get("aligned") is not None and abs(d["aligned"]) >= 0.3]
    top = sorted(moved, key=lambda d: -abs(d["aligned"]))[:3]
    detail = ", ".join(f"{d['name']} {d['pct']:+.2f}%" for d in top)
    cue, score = glob["cue"], glob["score"]
    helps_long = cue == "SUPPORTIVE"
    hurts_long = cue == "AGAINST"
    if (side is SignalType.BUY and helps_long) or (side is SignalType.SELL and hurts_long):
        pros.append(f"Global cues support the trade (net {score:+.2f}"
                    f"{': ' + detail if detail else ''})")
    elif (side is SignalType.BUY and hurts_long) or (side is SignalType.SELL and helps_long):
        cons.append(f"Global cues work against the trade (net {score:+.2f}"
                    f"{': ' + detail if detail else ''})")


def _verdict(side: SignalType, gate, rr: Optional[float], news: dict) -> tuple[str, str]:
    if gate.vetoed:
        return "AVOID", "Quality gate veto — event/fundamental risk overrides the setup."
    if side is SignalType.HOLD:
        return "NO TRADE", "No directional edge right now — indicators disagree."
    news_against = ((side is SignalType.BUY and news["net"] == "NEGATIVE")
                    or (side is SignalType.SELL and news["net"] == "POSITIVE"))
    if gate.passed and (rr or 0) >= 1.5 and not news_against:
        return "TAKE", "Setup passes all gates: confluence, quality and news align."
    if gate.passed:
        return "CAUTION", ("News flow conflicts with the signal — size down or wait."
                           if news_against else
                           "Setup passes but risk/reward is thin.")
    return "CAUTION", "Below quality threshold — treat as watch-only."


def analyze_frame(instr, df, *, style: str, headlines: list[str],
                  fundamentals: dict, event_flags: list[str],
                  global_cues: Optional[dict] = None) -> dict:
    """Pure full analysis from a candle frame (network inputs passed in)."""
    snap = build_confluence(df, regime=None, style=style,
                            active_ids=list(range(1, 30)))
    last = float(df["close"].iloc[-1])
    atr_val = float(ind.atr(df).dropna().iloc[-1])
    cs = signal_engine.generate(instr, snap, last_price=last, atr=atr_val,
                                mode="mock", cache={})
    gate = apply_gate(cs, fundamentals=fundamentals, event_flags=event_flags,
                      kind=instr.kind)
    news = classify_news(instr.symbol, headlines)
    readings = _indicator_readings(df)

    sd = cs.indicator_snapshot
    entry, sl, tgt = sd.get("entry"), sd.get("stop_loss"), sd.get("target")
    rr = None
    if entry is not None and sl is not None and tgt is not None and entry != sl:
        rr = round(abs(tgt - entry) / abs(entry - sl), 2)

    side = cs.consensus
    pros, cons = _pros_cons(side, snap, gate, news, readings, cs)
    _global_pros_cons(side, global_cues, pros, cons)
    verdict, verdict_why = _verdict(side, gate, rr, news)

    return {
        "symbol": instr.symbol, "kind": instr.kind, "style": style,
        "last": _fmt(last), "signal": side.value,
        "confidence": cs.avg_confidence, "agreement": cs.agreement_pct,
        "regime": snap.regime.value, "net_score": snap.net_score,
        "buy_count": snap.buy_count, "sell_count": snap.sell_count,
        "hold_count": snap.hold_count,
        "category_scores": {k: round(v, 3) for k, v in snap.category_scores.items()},
        "votes": [{"name": v.name, "category": v.category, "vote": v.vote.value,
                   "strength": v.strength, "detail": v.detail}
                  for v in sorted(snap.votes, key=lambda v: -v.strength)],
        "entry": entry, "stop_loss": sl, "target": tgt, "rr": rr, "atr": _fmt(atr_val),
        "gate": {"passed": gate.passed, "score": gate.score, "vetoed": gate.vetoed,
                 "reasons": gate.reasons, "cautions": gate.cautions},
        "readings": readings,
        "news": news, "event_flags": event_flags,
        "events": classify_corporate_events(instr.symbol, headlines),
        "fundamentals": fundamentals,
        "global": global_cues,
        "pros": pros, "cons": cons,
        "verdict": verdict, "verdict_why": verdict_why,
    }


def event_flags_for(symbol: str, headlines: list[str], today) -> list[str]:
    """Per-share event flags. EXPIRY/RBI are market-wide cautions, but RESULTS
    (the hard veto in the quality gate) only fires when an earnings headline
    mentions THIS share — a generic 'earnings season' story must not veto
    every stock in the universe."""
    flags: list[str] = []
    if today.weekday() == 3:                       # Thursday weekly index expiry
        flags.append("EXPIRY")
    blob = " ".join(headlines).lower()
    if any(k in blob for k in ("rbi", "fed", "policy", "rate decision")):
        flags.append("RBI")
    aliases = ALIASES.get(symbol.upper(), [symbol.lower()])
    stock_blob = " ".join(h.lower() for h in headlines
                          if any(a in h.lower() for a in aliases))
    if any(k in stock_blob for k in ("result", "earnings", "quarterly", "q1", "q2",
                                     "q3", "q4 ")):
        flags.append("RESULTS")
    return flags


def analyze(instr, df, *, style: str, news_fetch=None) -> dict:
    """Convenience wrapper: pulls cached news + fundamentals + world markets,
    then analyze_frame."""
    from datetime import date
    from services import global_markets
    headlines = cached_headlines(fetch=news_fetch)
    flags = event_flags_for(instr.symbol, headlines, date.today())
    funda = cached_fundamentals(instr.symbol, instr.kind)
    try:
        world = global_markets.snapshot()
        cues = global_markets.stock_drivers(instr.symbol, world) if world else None
    except Exception:                              # noqa: BLE001
        log.warning("global cues failed", exc_info=True)
        cues = None
    return analyze_frame(instr, df, style=style, headlines=headlines,
                         fundamentals=funda, event_flags=flags,
                         global_cues=cues)
