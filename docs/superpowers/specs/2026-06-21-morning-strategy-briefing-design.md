# Morning Strategy Briefing — Design

**Date:** 2026-06-21
**Status:** Approved
**Depends on:** regime classifier, indicators, news, providers (AI narrative), dhan_client

---

## 1. Purpose

A pre-market briefing that reads index regime, India VIX, index overbought/oversold,
and overnight/event news, then recommends **one preset to run today** with transparent
reasoning and caution flags — so the operator runs a regime-appropriate strategy instead
of picking blind.

**Honest framing:** picks the *regime-appropriate* preset and flags risk; it is NOT a
profit oracle. Rules are transparent; AI only writes the narrative. Backtest calibration
(slice 1) can later sharpen which preset wins per regime.

---

## 2. market_context.py (`services/market_context.py`)

```python
@dataclass
class MarketContext:
    regime: str                  # TRENDING | RANGING | VOLATILE | UNKNOWN
    vix: float | None
    index_rsi: float | None
    rsi_state: str               # OVERSOLD | OVERBOUGHT | NEUTRAL | UNKNOWN
    headlines: list[str]
    event_flags: list[str]       # e.g. EXPIRY, RBI, RESULTS (best-effort)
    as_of: str
```

- `build_context(index_instrument, vix_instrument=None, *, dhan_client,
  news_fetch=None, today=None) -> MarketContext`:
  - regime: `classify_regime(dhan_client.get_candles(index, "day", 60))`.
  - index_rsi: `indicators.rsi(daily close).iloc[-1]`; rsi_state from <30 / >70 / else.
  - vix: `dhan_client.get_ltp(vix_instrument)` if provided, else None (degrade).
  - headlines: `news.get_headlines(index.symbol, fetch=news_fetch)`.
  - event_flags: best-effort — EXPIRY if today is Thursday (weekly index expiry);
    keyword scan of headlines for "RBI"/"Fed"/"policy"→RBI, "result"/"earnings"→RESULTS.
  - All reads wrapped; any failure → that field None/empty, never raises.

---

## 3. strategy_selector.py (`services/strategy_selector.py`, pure)

```python
@dataclass
class Selection:
    preset: str                  # key in strategies.json presets
    reasons: list[str]
    cautions: list[str]
    extra_notes: list[str]       # e.g. positional_quality suggestion for equities
```

- `select(ctx: MarketContext) -> Selection` — deterministic rule map:
  - rsi_state OVERSOLD/OVERBOUGHT → `range_scalper` (+ reason: revert bias).
  - else regime TRENDING → `intraday_momentum`; if vix and vix high (>20) → caution "high VIX, size down"; extra_note positional_quality if vix low (<15).
  - regime RANGING → `range_scalper`.
  - regime VOLATILE or vix very high (>25) → `range_scalper` + caution "elevated volatility, defined-risk only / consider sitting out".
  - regime UNKNOWN → `range_scalper` (conservative) + caution "regime unknown".
  - event_flags non-empty → append cautions ("expiry day — avoid fresh naked positions", "RBI/policy — expect whipsaw", "results — single-stock event risk").
  - reasons always list the driving factors (regime, vix, rsi).

VIX thresholds (configurable defaults): low<15, high>20, very-high>25.

---

## 4. briefing.py (`services/briefing.py`)

- `narrative(ctx, selection, *, mode="mock", provider=None, client=None) -> str`:
  - mode="mock" → deterministic template sentence from ctx+selection.
  - mode="api" → build a short prompt, call one provider via `call_provider`; on failure
    fall back to the mock template (never blank).
- `morning_briefing(index, vix, *, dhan_client, mode, ...) -> dict` — orchestrates
  build_context → select → narrative; returns `{context, selection, narrative}`.

---

## 5. UI

A "🌅 Morning Briefing" button on the dashboard top → renders: recommended preset
(prominent), reasons, cautions (amber), and the narrative. Optionally sets the active
preset in session for the day. Manual trigger (scheduling out of scope).

---

## 6. Error / Edge Handling

- Index candles unavailable → regime UNKNOWN, conservative range_scalper + caution.
- VIX unresolved/unavailable → vix None, VIX-based rules skipped (no crash).
- News fetch fails → empty headlines, no event keywords.
- AI narrative failure → mock template.

---

## 7. Testing (TDD; UI manual)

- `strategy_selector`: each rule branch → expected preset + cautions (trending/ranging/
  volatile, oversold/overbought, high/low VIX, event flags, unknown regime).
- `market_context`: injected fake dhan_client + news_fetch → context fields populated;
  failures degrade (vix None, regime UNKNOWN). Thursday → EXPIRY flag.
- `briefing`: mock narrative contains preset + regime; api path with fake provider;
  fallback to template on provider error.

---

## 8. Out of Scope

Scheduled auto-run at a fixed time (manual button only), multi-index breadth, options
greeks in the decision, auto-applying the preset to live orders (it only recommends;
human still confirms each trade).
