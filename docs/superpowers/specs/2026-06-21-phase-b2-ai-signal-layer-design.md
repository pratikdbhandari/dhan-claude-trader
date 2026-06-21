# Phase B2 — AI Signal Layer Design

**Date:** 2026-06-21
**Status:** Approved ("go for b2", scope = all of B2)
**Depends on:** Phase A confluence engine, B1 dhan_client (candles/ltp), providers.json

---

## 1. Purpose

Turn the Phase A confluence snapshot + market context into reasoned AI trade signals.
Fan out concurrently to enabled providers (Claude/Groq/Cerebras/Mistral), each returns
strict JSON, aggregate into a simple consensus. Includes RSS news + yfinance
fundamentals as context. Fully testable with injected fake clients + mock mode — no
keys, no API spend.

**Principles:** AI recommends, human confirms (B3). One provider failing never breaks
the card (independent validate/retry/HOLD-fallback). 5-min cache per instrument caps
cost. Accuracy-weighted consensus is **Phase C** — B2 ships simple majority.

---

## 2. Components

| File | Responsibility |
|------|----------------|
| `services/news.py` | RSS headlines per symbol/sector (stdlib urllib+xml). Network fail → []. Pluggable API slot. |
| `services/fundamentals.py` | yfinance wrapper: P/E, EPS, earnings date. Cached. Equities only. Fail → {}. |
| `services/prompt.py` | Pure: build structured prompt from regime + confluence + indicators + news + fundamentals + position context. |
| `services/providers.py` | Load providers.json; build client per enabled+keyed provider (anthropic / openai-compat); `call_provider(spec, prompt) -> ProviderSignal` with strict-JSON parse → retry once → HOLD fallback. Client factory injectable. |
| `services/signal_engine.py` | Orchestrator `generate(...) -> ConsensusSignal`: confluence → context → prompt → concurrent fan-out → consensus. mock mode + 5-min cache. |
| `requirements.txt` | add `yfinance`. |

---

## 3. AI Contract

Each provider gets the structured prompt and must return strict JSON:
```json
{"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":num|null,
 "stop_loss":num|null,"target":num|null,"reasoning":"...","risk_reward_ratio":num|null}
```
`call_provider`: parse → on failure retry once → on second failure return
`ProviderSignal(signal=HOLD, confidence=0, error=True, reasoning="parse/api error: ...")`.
Records `latency_ms`. Never raises into the engine.

**Provider client kinds** (from providers.json `kind`):
- `anthropic` → `anthropic.Anthropic(api_key).messages.create(model, ...)`.
- `openai` → `openai.OpenAI(api_key, base_url).chat.completions.create(model, ...)`
  (serves Groq/Cerebras/Mistral via base_url).
Only providers with `enabled=true` AND a non-empty key (from `key_env`) are called.

---

## 4. Mock Mode

`SIGNAL_SOURCE=mock` (or no keys present): the engine skips real clients and produces
one deterministic `ProviderSignal(provider="mock")` from the confluence snapshot:
- `signal = snapshot.bias`
- `confidence = round(abs(net_score)*100)`
- `entry = last close`; `stop_loss`/`target` via ATR (1×ATR stop, 2×ATR target);
  `risk_reward_ratio = 2.0`
- `reasoning = "Mock: <regime>, net_score <x>, <buy>/<sell>/<hold> votes"`

Lets the whole pipeline + B3 UI + journal be tested free.

---

## 5. Consensus (simple, B2)

Over **active** (non-error) provider signals:
- `consensus` = majority vote of signals (tie → HOLD).
- `avg_confidence` = mean confidence of providers matching consensus (round int).
- `agreement_pct` = round(100 * matching / active count).
- entry/SL/target on the consensus card = median of matching providers' values.
If all providers errored → consensus HOLD, agreement 0.

---

## 6. Data Flow

```
candles (B1) → Phase A build_confluence → snapshot
news.get_headlines(symbol) ─┐
fundamentals.get(symbol) ───┤→ prompt.build(...) → prompt text
open-position context ──────┘
                              → providers fan-out (ThreadPoolExecutor, enabled+keyed)
                              → [ProviderSignal...]  (mock: single deterministic)
                              → consensus → ConsensusSignal
                              → (B3) risk gate → confirm → order → journal
5-min cache keyed by security_id: within window, return cached ConsensusSignal.
```

---

## 7. Error / Edge Handling

- News/fundamentals network failure → empty result, logged, pipeline continues.
- Provider API/parse failure → that ProviderSignal flagged `error=True`, HOLD; others unaffected.
- No enabled+keyed providers and not mock → engine falls back to mock with a logged warning (never empty).
- Cache: in-memory dict keyed by security_id → (timestamp, ConsensusSignal); `force=True` bypasses.
- yfinance only attempted for `kind=EQUITY` instruments.

---

## 8. Testing (TDD, no network/keys)

- `news`: monkeypatch urlopen with sample RSS XML → headlines parsed; network error → [].
- `fundamentals`: monkeypatch yfinance Ticker → dict; missing data → {}.
- `prompt`: pure — asserts prompt contains regime, votes, news, fundamentals, position.
- `providers`: fake client returning canned JSON → ProviderSignal; malformed JSON →
  retry then HOLD+error; latency recorded.
- `signal_engine`: mock mode deterministic signal from a known snapshot; api mode with
  injected fake providers → consensus math (majority, agreement%); cache returns same
  object within 5 min; force bypass.

---

## 9. Out of Scope (later)

Accuracy-weighted consensus + event/time guards (Phase C); risk gate, Streamlit UI,
confirm dialog (B3); EOD report (B4). No streaming responses. News API-key feed is a
config slot only (RSS is the B2 implementation).
