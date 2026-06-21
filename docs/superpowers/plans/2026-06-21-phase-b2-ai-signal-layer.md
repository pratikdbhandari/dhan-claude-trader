# Phase B2: AI Signal Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase A confluence snapshot + news + fundamentals into reasoned AI signals via concurrent multi-provider fan-out, aggregated into a simple consensus, with a deterministic mock mode and 5-min cache.

**Architecture:** Small focused modules: `news` (RSS), `fundamentals` (yfinance), `prompt` (pure builder), `providers` (client + JSON parse/retry/HOLD), `signal_engine` (orchestrate + consensus + mock + cache). Network and provider clients are injected for tests — zero API spend, no keys.

**Tech Stack:** Python 3.13, anthropic, openai (Groq/Cerebras/Mistral via base_url), yfinance, stdlib urllib/xml, concurrent.futures, pytest.

> **Caveat:** real provider response shapes/SDK calls are wrapped behind a tolerant parser; the `mock` + fake-client tests fully exercise the pipeline. Verify a real provider call once keys exist.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `services/news.py` | `get_headlines(symbol, hours, fetch=None) -> list[str]` |
| `services/fundamentals.py` | `get_fundamentals(symbol, ticker_factory=None) -> dict` |
| `services/prompt.py` | `build_prompt(...) -> str` (pure) |
| `services/providers.py` | `load_providers()`, `parse_signal(text, provider)`, `call_provider(spec, prompt, client)` |
| `services/signal_engine.py` | `generate(...) -> ConsensusSignal`, `mock_signal(...)`, `consensus(...)` |
| tests | one module per file |

---

## Task 1: News RSS

**Files:** Create `services/news.py`, `tests/test_news.py`.

> Parser is fed RSS XML text; `fetch(url)->str` is injected (default uses urllib).
> Returns `<title>` texts. Network/parse error → `[]` (logged, never raises).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_news.py
from services import news

SAMPLE = """<?xml version="1.0"?><rss><channel>
<item><title>Nifty hits record high</title></item>
<item><title>RBI holds repo rate</title></item>
</channel></rss>"""

def test_parses_titles_from_rss():
    out = news.get_headlines("NIFTY", hours=24, fetch=lambda url: SAMPLE)
    assert "Nifty hits record high" in out
    assert "RBI holds repo rate" in out

def test_network_error_returns_empty():
    def boom(url): raise OSError("no net")
    assert news.get_headlines("NIFTY", hours=24, fetch=boom) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_news.py -v`
Expected: FAIL `ModuleNotFoundError: services.news`

- [ ] **Step 3: Implement `services/news.py`**

```python
"""RSS news headlines. Pure-ish: fetch() is injectable so tests pass XML directly.
Network/parse failures degrade to an empty list (never raise)."""
from __future__ import annotations
import logging
import xml.etree.ElementTree as ET
from urllib.request import urlopen

log = logging.getLogger(__name__)

# Default Indian market feeds; pluggable. (Symbol filtering is best-effort on title.)
FEEDS = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]


def _default_fetch(url: str) -> str:
    with urlopen(url, timeout=5) as r:        # noqa: S310
        return r.read().decode("utf-8", "ignore")


def get_headlines(symbol: str, hours: int = 24, fetch=None, feeds=None) -> list[str]:
    fetch = fetch or _default_fetch
    feeds = feeds if feeds is not None else FEEDS
    titles: list[str] = []
    for url in feeds:
        try:
            xml = fetch(url)
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                t = item.findtext("title")
                if t:
                    titles.append(t.strip())
        except Exception as e:                # noqa: BLE001
            log.warning("news feed failed %s: %s", url, e)
            continue
    return titles
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_news.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/news.py tests/test_news.py
git commit -m "feat(news): RSS headline fetcher (injectable, fail-safe)"
```

---

## Task 2: Fundamentals (yfinance)

**Files:** Create `services/fundamentals.py`, `tests/test_fundamentals.py`.

> `ticker_factory(symbol)->obj` injected; default wraps `yfinance.Ticker`. Reads
> `.info` dict. Missing/error → `{}`. Appends `.NS` for NSE symbols.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fundamentals.py
from services import fundamentals

class FakeTicker:
    def __init__(self, info): self.info = info

def test_extracts_key_fundamentals():
    fac = lambda sym: FakeTicker({"trailingPE": 25.3, "trailingEps": 88.0,
                                  "marketCap": 1e12})
    out = fundamentals.get_fundamentals("RELIANCE", ticker_factory=fac)
    assert out["pe"] == 25.3 and out["eps"] == 88.0
    assert out["market_cap"] == 1e12

def test_error_returns_empty():
    def boom(sym): raise RuntimeError("yf down")
    assert fundamentals.get_fundamentals("X", ticker_factory=boom) == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_fundamentals.py -v`
Expected: FAIL `ModuleNotFoundError: services.fundamentals`

- [ ] **Step 3: Implement `services/fundamentals.py`**

```python
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
        return {
            "pe": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "market_cap": info.get("marketCap"),
            "earnings_date": info.get("earningsDate"),
        }
    except Exception as e:                     # noqa: BLE001
        log.warning("fundamentals failed for %s: %s", symbol, e)
        return {}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_fundamentals.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/fundamentals.py tests/test_fundamentals.py
git commit -m "feat(fundamentals): yfinance wrapper (injectable, fail-safe)"
```

---

## Task 3: Prompt builder (pure)

**Files:** Create `services/prompt.py`, `tests/test_prompt.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt.py
from services.prompt import build_prompt
from core.models import ConfluenceSnapshot, Regime, SignalType, StrategyVote

def _snap():
    v = StrategyVote(1, "ema_cross", "trend", SignalType.BUY, 70, "x")
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[v],
                              category_scores={"trend": 0.7}, net_score=0.35,
                              bias=SignalType.BUY, buy_count=1, sell_count=0, hold_count=0)

def test_prompt_contains_all_sections():
    p = build_prompt(symbol="NIFTY", snapshot=_snap(), last_price=22000,
                     indicators={"rsi": 61.2}, news=["RBI holds rate"],
                     fundamentals={"pe": 25.3}, position="none")
    for token in ["NIFTY", "TRENDING", "ema_cross", "RBI holds rate", "25.3",
                  "22000", "JSON", "signal"]:
        assert token in p

def test_prompt_handles_empty_context():
    p = build_prompt(symbol="X", snapshot=_snap(), last_price=100,
                     indicators={}, news=[], fundamentals={}, position="none")
    assert "X" in p and "JSON" in p
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_prompt.py -v`
Expected: FAIL `ModuleNotFoundError: services.prompt`

- [ ] **Step 3: Implement `services/prompt.py`**

```python
"""Pure prompt builder. Assembles the structured context the AI providers see."""
from __future__ import annotations
from core.models import ConfluenceSnapshot

_INSTRUCTION = (
    "You are a disciplined intraday/positional trading assistant for Indian markets. "
    "Given the technical confluence, news and fundamentals below, respond with STRICT "
    "JSON only (no prose) of the form: "
    '{"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":number|null,'
    '"stop_loss":number|null,"target":number|null,"reasoning":"...",'
    '"risk_reward_ratio":number|null}.'
)


def build_prompt(*, symbol: str, snapshot: ConfluenceSnapshot, last_price: float,
                 indicators: dict, news: list[str], fundamentals: dict,
                 position: str) -> str:
    votes = "; ".join(f"{v.name}={v.vote.value}({v.strength})" for v in snapshot.votes)
    cats = ", ".join(f"{k}:{round(s, 2)}" for k, s in snapshot.category_scores.items())
    ind = ", ".join(f"{k}={v}" for k, v in indicators.items()) or "n/a"
    nws = " | ".join(news[:8]) or "none"
    fnd = ", ".join(f"{k}={v}" for k, v in fundamentals.items() if v is not None) or "n/a"
    return "\n".join([
        _INSTRUCTION,
        f"Instrument: {symbol}",
        f"Last price: {last_price}",
        f"Regime: {snapshot.regime.value}",
        f"Confluence bias: {snapshot.bias.value} (net_score {snapshot.net_score})",
        f"Category scores: {cats}",
        f"Votes ({snapshot.buy_count}B/{snapshot.sell_count}S/{snapshot.hold_count}H): {votes}",
        f"Indicators: {ind}",
        f"News: {nws}",
        f"Fundamentals: {fnd}",
        f"Open position: {position}",
    ])
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_prompt.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/prompt.py tests/test_prompt.py
git commit -m "feat(prompt): pure structured prompt builder"
```

---

## Task 4: Providers — load + parse_signal

**Files:** Create `services/providers.py`, `tests/test_providers.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_providers.py
from services.providers import parse_signal, load_providers
from core.models import ProviderSignal, SignalType

def test_parse_valid_json():
    txt = ('{"signal":"BUY","confidence":72,"entry":100,"stop_loss":98,'
           '"target":104,"reasoning":"trend up","risk_reward_ratio":2.0}')
    sig = parse_signal(txt, provider="groq")
    assert isinstance(sig, ProviderSignal)
    assert sig.signal is SignalType.BUY and sig.confidence == 72
    assert sig.error is False and sig.provider == "groq"

def test_parse_json_embedded_in_text():
    txt = 'Here you go: {"signal":"SELL","confidence":60,"reasoning":"weak"} thanks'
    sig = parse_signal(txt, provider="claude")
    assert sig.signal is SignalType.SELL and sig.error is False

def test_parse_garbage_returns_none():
    assert parse_signal("not json at all", provider="x") is None

def test_load_providers_returns_list():
    provs = load_providers()
    names = {p["name"] for p in provs}
    assert {"claude", "groq", "cerebras", "mistral"}.issubset(names)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL `ModuleNotFoundError: services.providers`

- [ ] **Step 3: Implement `services/providers.py`** (parse + load only; call_provider in Task 5)

```python
"""AI provider adapters: load registry, parse strict-JSON into ProviderSignal."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional
from core.models import ProviderSignal, SignalType

_PROVIDERS_PATH = Path(__file__).resolve().parent.parent / "providers.json"


def load_providers() -> list[dict]:
    return json.loads(_PROVIDERS_PATH.read_text())["providers"]


def parse_signal(text: str, provider: str) -> Optional[ProviderSignal]:
    """Parse the first JSON object in text into a ProviderSignal. None on failure."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        d = json.loads(match.group(0))
        return ProviderSignal(
            provider=provider,
            signal=SignalType(d["signal"].upper()),
            confidence=int(d.get("confidence", 0)),
            entry=d.get("entry"), stop_loss=d.get("stop_loss"),
            target=d.get("target"),
            risk_reward_ratio=d.get("risk_reward_ratio"),
            reasoning=str(d.get("reasoning", "")),
            error=False)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_providers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/providers.py tests/test_providers.py
git commit -m "feat(providers): registry load + strict-JSON signal parser"
```

---

## Task 5: Providers — call_provider (parse→retry→HOLD)

**Files:** Modify `services/providers.py`; Test add to `tests/test_providers.py`.

> `call_provider(spec, prompt, client)` — `client(prompt) -> str` is the injected
> provider call (real clients built elsewhere). Parse; on None retry once; on second
> failure return HOLD with `error=True`. Records `latency_ms`.

- [ ] **Step 1: Write the failing test (append)**

```python
from services.providers import call_provider
from core.models import SignalType

_SPEC = {"name": "groq", "model": "m"}

def test_call_provider_success():
    client = lambda prompt: '{"signal":"BUY","confidence":80,"reasoning":"ok"}'
    sig = call_provider(_SPEC, "p", client=client)
    assert sig.signal is SignalType.BUY and sig.error is False
    assert sig.latency_ms is not None

def test_call_provider_retries_then_holds():
    calls = {"n": 0}
    def flaky(prompt):
        calls["n"] += 1
        return "garbage"            # always unparseable
    sig = call_provider(_SPEC, "p", client=flaky)
    assert sig.signal is SignalType.HOLD and sig.error is True
    assert calls["n"] == 2          # original + one retry

def test_call_provider_exception_holds():
    def boom(prompt): raise RuntimeError("api 500")
    sig = call_provider(_SPEC, "p", client=boom)
    assert sig.signal is SignalType.HOLD and sig.error is True
    assert "api 500" in sig.reasoning
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL `ImportError: cannot import name 'call_provider'`

- [ ] **Step 3: Append to `services/providers.py`**

```python
import time


def call_provider(spec: dict, prompt: str, client) -> ProviderSignal:
    """client(prompt) -> str. Parse → retry once → HOLD fallback. Never raises."""
    name = spec["name"]
    start = time.time()
    last_err = ""
    for attempt in range(2):
        try:
            text = client(prompt)
            sig = parse_signal(text, provider=name)
            if sig is not None:
                sig.latency_ms = int((time.time() - start) * 1000)
                return sig
            last_err = "unparseable response"
        except Exception as e:                 # noqa: BLE001
            last_err = str(e)
    return ProviderSignal(
        provider=name, signal=SignalType.HOLD, confidence=0,
        entry=None, stop_loss=None, target=None, risk_reward_ratio=None,
        reasoning=f"parse/api error: {last_err}", error=True,
        latency_ms=int((time.time() - start) * 1000))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_providers.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add services/providers.py tests/test_providers.py
git commit -m "feat(providers): call_provider with retry + HOLD fallback"
```

---

## Task 6: signal_engine — mock_signal + consensus

**Files:** Create `services/signal_engine.py`; Test `tests/test_signal_engine.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_engine.py
import pytest
from services.signal_engine import mock_signal, consensus
from core.models import (ConfluenceSnapshot, Regime, SignalType, StrategyVote,
                         ProviderSignal)

def _snap(bias=SignalType.BUY, net=0.4):
    v = StrategyVote(1, "ema", "trend", bias, 70, "x")
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[v],
                              category_scores={"trend": net}, net_score=net,
                              bias=bias, buy_count=1, sell_count=0, hold_count=0)

def test_mock_signal_from_snapshot():
    sig = mock_signal(_snap(SignalType.BUY, 0.4), last_price=100.0, atr=2.0)
    assert sig.provider == "mock"
    assert sig.signal is SignalType.BUY
    assert sig.confidence == 40            # round(0.4*100)
    assert sig.entry == 100.0
    assert sig.stop_loss == 98.0 and sig.target == 104.0   # 1xATR / 2xATR

def _ps(sig, conf):
    return ProviderSignal(provider="p", signal=sig, confidence=conf, entry=100,
                          stop_loss=98, target=104, risk_reward_ratio=2.0,
                          reasoning="r")

def test_consensus_majority_and_agreement():
    sigs = [_ps(SignalType.BUY, 80), _ps(SignalType.BUY, 70), _ps(SignalType.SELL, 60)]
    c = consensus(sigs)
    assert c["consensus"] is SignalType.BUY
    assert c["avg_confidence"] == 75        # mean of the two BUYs
    assert c["agreement_pct"] == 67         # 2 of 3

def test_consensus_all_errored_is_hold():
    e = ProviderSignal(provider="p", signal=SignalType.HOLD, confidence=0, entry=None,
                       stop_loss=None, target=None, risk_reward_ratio=None,
                       reasoning="err", error=True)
    c = consensus([e])
    assert c["consensus"] is SignalType.HOLD and c["agreement_pct"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL `ModuleNotFoundError: services.signal_engine`

- [ ] **Step 3: Implement `services/signal_engine.py`** (mock + consensus first)

```python
"""AI signal orchestration: mock signal, consensus, and (Task 7) full generate()."""
from __future__ import annotations
import statistics
from collections import Counter
from core.models import ConfluenceSnapshot, ProviderSignal, SignalType


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
    # tie => HOLD
    if list(counts.values()).count(n) > 1:
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/signal_engine.py tests/test_signal_engine.py
git commit -m "feat(signal_engine): mock signal + simple consensus"
```

---

## Task 7: signal_engine — generate() with fan-out + cache

**Files:** Modify `services/signal_engine.py`; Test add to `tests/test_signal_engine.py`.

> `generate(instrument, snapshot, last_price, atr, *, mode, providers=None,
> client_factory=None, news_list=None, fundamentals_dict=None, position="none",
> indicators=None, force=False, cache=None, cooldown=300) -> ConsensusSignal`.
> `mode="mock"` → single mock signal. `mode="api"` → fan out via ThreadPoolExecutor
> over `providers` (list of specs), each calling `client_factory(spec)(prompt)`; if no
> providers → falls back to mock with a warning. 5-min cache keyed by security_id.

- [ ] **Step 1: Write the failing test (append)**

```python
from services.signal_engine import generate
from core.models import Instrument, ConsensusSignal

def _instr():
    return Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                      kind="INDEX")

def test_generate_mock_mode():
    cs = generate(_instr(), _snap(SignalType.BUY, 0.4), last_price=100, atr=2.0,
                  mode="mock")
    assert isinstance(cs, ConsensusSignal)
    assert cs.consensus is SignalType.BUY
    assert cs.providers[0].provider == "mock"

def test_generate_api_mode_with_fake_clients():
    specs = [{"name": "groq", "model": "m"}, {"name": "claude", "model": "m"}]
    def factory(spec):
        return lambda prompt: '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
    cs = generate(_instr(), _snap(SignalType.BUY, 0.4), last_price=100, atr=2.0,
                  mode="api", providers=specs, client_factory=factory)
    assert cs.consensus is SignalType.BUY
    assert len(cs.providers) == 2
    assert cs.agreement_pct == 100

def test_generate_caches_within_cooldown():
    cache = {}
    calls = {"n": 0}
    def factory(spec):
        def c(prompt):
            calls["n"] += 1
            return '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
        return c
    specs = [{"name": "groq", "model": "m"}]
    a = generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
                 client_factory=factory, cache=cache)
    b = generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
                 client_factory=factory, cache=cache)
    assert a is b                      # served from cache
    assert calls["n"] == 1             # provider called once only

def test_generate_force_bypasses_cache():
    cache = {}
    calls = {"n": 0}
    def factory(spec):
        def c(prompt):
            calls["n"] += 1
            return '{"signal":"BUY","confidence":70,"reasoning":"ok"}'
        return c
    specs = [{"name": "groq", "model": "m"}]
    generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
             client_factory=factory, cache=cache)
    generate(_instr(), _snap(), 100, 2.0, mode="api", providers=specs,
             client_factory=factory, cache=cache, force=True)
    assert calls["n"] == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL `ImportError: cannot import name 'generate'`

- [ ] **Step 3: Append to `services/signal_engine.py`**

```python
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from core.models import ConsensusSignal, Instrument
from services.prompt import build_prompt
from services.providers import call_provider

log = logging.getLogger(__name__)


def _build(instrument, snapshot, parts, last_price) -> ConsensusSignal:
    return ConsensusSignal(
        instrument=instrument, providers=parts["signals"],
        consensus=parts["consensus"], avg_confidence=parts["avg_confidence"],
        agreement_pct=parts["agreement_pct"],
        indicator_snapshot={"regime": snapshot.regime.value,
                            "net_score": snapshot.net_score})


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
```
(Remove the unused `_build` helper if your linter flags it — it is illustrative; the
inline construction in `generate` is what runs.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add services/signal_engine.py tests/test_signal_engine.py
git commit -m "feat(signal_engine): generate() fan-out + consensus + 5-min cache"
```

---

## Task 8: Real client factory (thin, behind injection)

**Files:** Modify `services/providers.py`; Test add to `tests/test_providers.py`.

> `make_client(spec, api_key)` returns a `client(prompt)->str` closure for real use.
> `kind=anthropic` → anthropic SDK; `kind=openai` → openai SDK with base_url. Tested
> only for the dispatch decision (which SDK path) using fake SDK modules injected via
> params — NO network. Real call shapes are wrapped; verify with a live key later.

- [ ] **Step 1: Write the failing test (append)**

```python
from services.providers import make_client

def test_make_client_openai_kind_uses_base_url():
    captured = {}
    class FakeOpenAI:
        def __init__(self, api_key, base_url): captured["base_url"] = base_url
        class chat:  # noqa
            pass
    # inject via _openai_cls / _anthropic_cls params
    spec = {"name": "groq", "kind": "openai", "model": "m",
            "base_url": "https://api.groq.com/openai/v1"}
    client = make_client(spec, api_key="k", _openai_cls=FakeOpenAI)
    assert callable(client)
    assert captured["base_url"] == "https://api.groq.com/openai/v1"

def test_make_client_anthropic_kind():
    captured = {}
    class FakeAnthropic:
        def __init__(self, api_key): captured["ok"] = True
    spec = {"name": "claude", "kind": "anthropic", "model": "m", "base_url": None}
    client = make_client(spec, api_key="k", _anthropic_cls=FakeAnthropic)
    assert callable(client) and captured["ok"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_providers.py -v`
Expected: FAIL `ImportError: cannot import name 'make_client'`

- [ ] **Step 3: Append to `services/providers.py`**

```python
def make_client(spec: dict, api_key: str, _openai_cls=None, _anthropic_cls=None):
    """Return client(prompt)->str for a real provider. SDK classes injectable for tests."""
    kind = spec.get("kind", "openai")
    model = spec["model"]
    if kind == "anthropic":
        if _anthropic_cls is None:
            from anthropic import Anthropic as _anthropic_cls   # noqa: N806
        sdk = _anthropic_cls(api_key=api_key)

        def call(prompt: str) -> str:
            resp = sdk.messages.create(
                model=model, max_tokens=512,
                messages=[{"role": "user", "content": prompt}])
            return resp.content[0].text
        return call

    if _openai_cls is None:
        from openai import OpenAI as _openai_cls               # noqa: N806
    sdk = _openai_cls(api_key=api_key, base_url=spec.get("base_url"))

    def call(prompt: str) -> str:
        resp = sdk.chat.completions.create(
            model=model, max_tokens=512,
            messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content
    return call
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_providers.py -v`
Expected: PASS (9 passed) — the fake SDK classes only need to be constructed; the
returned `call` closure is not invoked in these tests.

- [ ] **Step 5: Commit**

```bash
git add services/providers.py tests/test_providers.py
git commit -m "feat(providers): make_client factory (anthropic/openai, injectable)"
```

---

## Task 9: Integration — full pipeline mock + api

**Files:** Test `tests/test_b2_integration.py`.

- [ ] **Step 1: Write the test**

```python
# tests/test_b2_integration.py
"""B2 end-to-end: candles -> confluence -> signal_engine consensus (mock + api)."""
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.strategies.engine import build_confluence
from services.signal_engine import generate
from core.models import Instrument, ConsensusSignal, SignalType

def _instr():
    return Instrument(symbol="X", exchange_segment="NSE_EQ", security_id="1",
                      kind="EQUITY")

def test_pipeline_mock(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    cs = generate(_instr(), snap, last_price=float(trending_candles["close"].iloc[-1]),
                  atr=1.5, mode="mock")
    assert isinstance(cs, ConsensusSignal)
    assert cs.consensus in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert cs.providers[0].provider == "mock"

def test_pipeline_api_fake_providers(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    specs = [{"name": "groq", "model": "m"}, {"name": "mistral", "model": "m"}]
    factory = lambda spec: (lambda prompt:
        '{"signal":"BUY","confidence":75,"entry":100,"stop_loss":98,'
        '"target":104,"reasoning":"ok","risk_reward_ratio":2.0}')
    cs = generate(_instr(), snap, last_price=100.0, atr=1.5, mode="api",
                  providers=specs, client_factory=factory)
    assert cs.consensus is SignalType.BUY and len(cs.providers) == 2
    assert cs.agreement_pct == 100
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest tests/test_b2_integration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 3: Run FULL suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_b2_integration.py
git commit -m "test: B2 integration — confluence to AI consensus (mock + api)"
```

---

## Self-Review Notes (completed)

- **Spec coverage:** §2 news → Task 1; fundamentals → Task 2; prompt → Task 3;
  providers (load/parse/call/factory) → Tasks 4-5,8; signal_engine (mock/consensus/
  generate/cache) → Tasks 6-7. §3 AI contract → Tasks 4-5. §4 mock → Task 6. §5
  consensus → Task 6. §6 data flow → Task 9. §7 error handling: news/fund fail-safe
  (1-2), provider retry/HOLD (5), no-provider→mock fallback (7). §8 testing → all TDD
  with injected fakes.
- **Type consistency:** `ProviderSignal` (provider, signal, confidence, entry,
  stop_loss, target, risk_reward_ratio, reasoning, error, latency_ms) and
  `ConsensusSignal` (instrument, providers, consensus, avg_confidence, agreement_pct,
  indicator_snapshot) used as defined in core/models.py. `generate`/`consensus`/
  `mock_signal`/`call_provider`/`make_client` signatures stable across tasks/tests.
- **Placeholder scan:** all code complete. `_build` helper in Task 7 flagged as
  removable illustrative code, not a placeholder; real path is inline.
- **Execution order:** Tasks 1-3 independent (news, fundamentals, prompt). Task 4
  before 5 before 8 (same file, providers.py). Task 6 before 7 (signal_engine.py).
  Task 9 depends on all.
