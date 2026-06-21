"""AI signal orchestration: mock signal, consensus, and the full generate() pipeline."""
from __future__ import annotations
import logging
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from core.models import (ConfluenceSnapshot, ConsensusSignal, Instrument,
                         ProviderSignal, SignalType)
from services.prompt import build_prompt
from services.providers import call_provider

log = logging.getLogger(__name__)


def mock_signal(snapshot: ConfluenceSnapshot, last_price: float,
                atr: float) -> ProviderSignal:
    bias = snapshot.bias
    conf = round(abs(snapshot.net_score) * 100)
    if bias is SignalType.BUY:
        sl, tgt = round(last_price - atr, 2), round(last_price + 2 * atr, 2)
    elif bias is SignalType.SELL:
        sl, tgt = round(last_price + atr, 2), round(last_price - 2 * atr, 2)
    else:
        sl = tgt = None
    return ProviderSignal(
        provider="mock", signal=bias, confidence=conf,
        entry=last_price, stop_loss=sl, target=tgt,
        risk_reward_ratio=2.0 if bias is not SignalType.HOLD else None,
        reasoning=(f"Mock: {snapshot.regime.value}, net_score {snapshot.net_score}, "
                   f"{snapshot.buy_count}B/{snapshot.sell_count}S/{snapshot.hold_count}H"),
        error=False)


def _median(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 2) if vals else None


def consensus(signals: list[ProviderSignal]) -> dict:
    active = [s for s in signals if not s.error]
    if not active:
        return {"consensus": SignalType.HOLD, "avg_confidence": 0,
                "agreement_pct": 0, "entry": None, "stop_loss": None, "target": None}
    counts = Counter(s.signal for s in active)
    top, n = counts.most_common(1)[0]
    if list(counts.values()).count(n) > 1:        # tie => HOLD
        top = SignalType.HOLD
    matching = [s for s in active if s.signal is top]
    avg_conf = round(statistics.mean(s.confidence for s in matching)) if matching else 0
    return {
        "consensus": top,
        "avg_confidence": avg_conf,
        "agreement_pct": round(100 * len(matching) / len(active)),
        "entry": _median(s.entry for s in matching),
        "stop_loss": _median(s.stop_loss for s in matching),
        "target": _median(s.target for s in matching),
    }


def generate(instrument: Instrument, snapshot: ConfluenceSnapshot, last_price: float,
             atr: float, *, mode: str, providers=None, client_factory=None,
             news_list=None, fundamentals_dict=None, position="none",
             indicators=None, force=False, cache=None, cooldown: int = 300):
    key = instrument.security_id
    if cache is not None and not force and key in cache:
        ts, cached = cache[key]
        if time.time() - ts < cooldown:
            return cached

    if mode == "mock" or not providers:
        if mode != "mock":
            log.warning("no providers configured; falling back to mock")
        signals = [mock_signal(snapshot, last_price, atr)]
    else:
        prompt = build_prompt(symbol=instrument.symbol, snapshot=snapshot,
                              last_price=last_price, indicators=indicators or {},
                              news=news_list or [], fundamentals=fundamentals_dict or {},
                              position=position)

        def run(spec):
            return call_provider(spec, prompt, client=client_factory(spec))

        with ThreadPoolExecutor(max_workers=max(1, len(providers))) as ex:
            signals = list(ex.map(run, providers))

    c = consensus(signals)
    result = ConsensusSignal(
        instrument=instrument, providers=signals, consensus=c["consensus"],
        avg_confidence=c["avg_confidence"], agreement_pct=c["agreement_pct"],
        indicator_snapshot={"regime": snapshot.regime.value,
                            "net_score": snapshot.net_score,
                            "entry": c["entry"], "stop_loss": c["stop_loss"],
                            "target": c["target"]})
    if cache is not None:
        cache[key] = (time.time(), result)
    return result
