# Dhan-Claude Trader — Trading Strategy Design

**Date:** 2026-06-21
**Status:** Approved (pending final user review of this spec)
**Owner:** Solo operator (Pune), single Dhan account

---

## 1. Purpose & Guiding Principles

Define the trading-signal logic for the Dhan-Claude Trader — a local, single-user
desktop assistant where **AI recommends and the human confirms every trade**. This
spec covers *what signals are produced and how*, not the broker/UI plumbing (covered
by the original build spec).

**Non-negotiable principles:**

- **No "zero false signals."** No strategy or AI gives certainty; markets are partly
  random. The system maximises *expected edge and robustness*, never promising
  certainty. Confluence + AI judgment + human confirm reduce — never eliminate — bad trades.
- **Mechanical vs judgment separation.** Strategies compute votes mechanically;
  the AI layer applies judgment. Each is independently testable.
- **AI recommends, human confirms.** Nothing auto-fires. Two-step UI confirm is the
  final filter.
- **Config-driven.** Strategies, presets, providers, watchlist are all editable JSON.
- **Self-improving loop.** Journal outcomes feed adaptive weights back into signals.
- **Honest about over-optimization.** Backtesting uses out-of-sample / walk-forward
  splits to guard against curve-fitting. No tuning-to-perfection.

---

## 2. Per-Instrument Style

Each watchlist instrument carries a `style`:

- **intraday** — index futures, weekly index options. 5m + 15m candles. Squares off intraday.
- **positional** — large-cap NSE equities. Daily candles. Holds days–weeks; uses fundamentals.

Intraday-only strategies auto-disable for positional instruments and vice-versa.

---

## 3. Strategy Catalog (29 strategies)

Each strategy outputs `{vote: BUY|SELL|HOLD, strength: 0-100}`. `intraday_only`
strategies are skipped for positional instruments.

### A. Trend / Momentum
1. EMA crossover (9/21)
2. EMA ribbon alignment (8/13/21/34/55 stacked)
3. MACD signal-line crossover
4. MACD histogram momentum turn
5. ADX > 25 + DI+/DI− crossover
6. Supertrend flip
7. Parabolic SAR flip
8. Price vs 200-EMA regime filter
9. Market structure (HH/HL vs LL/LH)

### B. Mean-Reversion
10. RSI(14) oversold/overbought (<30 / >70)
11. RSI divergence vs price
12. Bollinger Band touch + reversal
13. Stochastic oversold/overbought crossover
14. Williams %R extremes
15. CCI extremes (±100)
16. VWAP reversion *(intraday_only)*
17. Z-score distance from mean

### C. Breakout / Volatility
18. Bollinger squeeze → breakout
19. Donchian channel(20) breakout
20. Opening Range Breakout *(intraday_only)*
21. ATR expansion breakout
22. Previous-day high/low break
23. Keltner channel breakout

### D. Volume
24. Volume spike confirmation (>1.5× avg)
25. OBV trend
26. VWAP cross *(intraday_only)*
27. Volume-weighted breakout

### E. Multi-timeframe / Structure
28. Multi-timeframe trend alignment (15m + daily agree)
29. Pivot-point S/R reaction *(intraday_only)*

### Preset Bundles (`strategies.json`)
- **Intraday Momentum Pack:** 1, 3, 5, 6, 8, 20, 24, 26, 28
- **Range Scalper Pack:** 10, 12, 13, 16, 17, 22, 29
- **Positional Quality Pack:** 2, 8, 9, 18, 19, 25, 28 + fundamentals overlay
- **Custom:** user toggles any of the 29
- **All-on:** all eligible strategies vote

> Presets are reasoned *starting points*, not proven optima. Actual best combos are
> determined empirically via the backtest harness + journal stats.

---

## 4. Optimized Signal Pipeline

Per instrument, per refresh (subject to 5-min cooldown):

```
[0] REGIME CLASSIFIER (ADX/ATR) → trending | ranging | volatile
      → selects eligible strategies; regime passed to AI
[1] STRATEGY ENGINE — eligible strategies vote {vote, strength}
      → CATEGORY-WEIGHTED aggregation (decorrelated: correlated indicators
        within a category don't fake conviction)
      → ADAPTIVE WEIGHTS applied (journal hit-rate per instrument/regime)
      → "confluence snapshot"
[2] CONTEXT ASSEMBLY
      ├─ RSS news (symbol/sector, last N hours)
      ├─ yfinance fundamentals + earnings proximity (equities only)
      ├─ event/time guards (expiry, RBI/Fed, open/close window)
      ├─ ATR snapshot (for adaptive SL/target)
      └─ open-position context
[3] AI LAYER — concurrent fan-out to enabled+keyed providers
      (Claude · Groq · Cerebras · Mistral)
      each returns strict JSON; validate → retry once → HOLD fallback
[4] CONSENSUS — weighted by per-provider accuracy (EOD leaderboard)
      → side-by-side + consensus card
[5] RISK GATE (pre-trade) → TWO-STEP HUMAN CONFIRM → place_order → JOURNAL
      → outcomes feed back to adaptive weights (loop closed)
```

### Optimizations (all included)
- **Regime gate** — only regime-appropriate strategies vote.
- **Decorrelated confluence** — weight by *cross-category* agreement, not raw count.
- **Adaptive weighting** — per-strategy realized hit-rate per instrument/regime, learned from journal.
- **ATR-adaptive stops/targets** — volatility-scaled, not fixed.
- **Event/time guards** — earnings, RBI/Fed, weekly expiry, open/close windows flagged to AI.
- **Per-provider accuracy weighting** — consensus weights providers by tracked accuracy.

---

## 5. AI Contract

Each provider receives a structured prompt: regime, confluence snapshot (per-category
+ per-strategy detail), live indicator values, news headlines, fundamentals (equities),
event flags, ATR, and open-position context.

Required strict JSON response:

```json
{
  "signal": "BUY|SELL|HOLD",
  "confidence": 0-100,
  "entry": number|null,
  "stop_loss": number|null,
  "target": number|null,
  "reasoning": "string",
  "risk_reward_ratio": number|null
}
```

Validation: parse → on failure retry once → on second failure fall back to
`HOLD` with `error=true`. Never crash, never fabricate. Each provider validated
independently so one failure never breaks the card.

**Mock mode:** strategy engine runs fully; AI layer replaced by a deterministic
rule mapping the confluence snapshot → signal. Entire flow testable with no API keys/cost.

---

## 6. Data Sources

| Data | Source | Dependency | Notes |
|------|--------|------------|-------|
| Candles, LTP, positions, funds, orders | Dhan (`dhanhq`) | existing | per build spec |
| Indicators | `ta` | existing | RSI/MACD/BB/ATR/etc. |
| News | RSS (Moneycontrol/ET/BS) via stdlib XML; pluggable API later | none (stdlib) | API-key slot in `.env`, blank = RSS |
| Fundamentals | `yfinance` (`SYMBOL.NS`) | **new (approved)** | equities only; unofficial, cached |
| AI | `anthropic` + `openai` (Groq/Cerebras/Mistral via base_url) | new (approved) | config-driven registry |

---

## 7. Config Files

- `strategies.json` — **new** — 29 strategies (id, category, params, `intraday_only`) + preset bundles.
- `watchlist.json` — **extended** — per-instrument `style`, `preset`, `strategy_overrides`.
- `providers.json` — existing — AI registry.
- `.env` — extended — optional `NEWS_API_KEY` slot.

---

## 8. Module Map

| Module | Status | Role |
|--------|--------|------|
| `core/config.py`, `core/models.py`, `core/utils.py` | built (Stage 0) | foundation |
| `services/dhan_client.py` | pending (Stage 1) | broker wrapper, dry_run aware |
| `services/regime.py` | new | regime classifier |
| `services/strategies/` (one file per category + `engine.py`) | new | compute & aggregate votes |
| `services/news.py` | new | RSS now, pluggable API |
| `services/fundamentals.py` | new | yfinance wrapper, cached |
| `services/signal_engine.py` | new | context assembly + AI fan-out + consensus |
| `services/risk_manager.py` | pending | pre-trade gate |
| `services/backtest.py` | new (Phase D) | historical replay, out-of-sample |
| `data/repository.py`, `data/journal.py` | pending/extended | SQLite + per-strategy/provider outcomes |
| `app.py`, `ui/` | pending | dashboard, confirm dialog, EOD report |

---

## 9. Build Phasing

- **Phase A — Strategy foundation:** Stage 1 `dhan_client` + `regime.py` +
  `services/strategies/` + category-weighted confluence. Testable with mock AI, no keys/cost.
- **Phase B — AI signals:** `signal_engine` AI fan-out + consensus + `news.py` +
  `fundamentals.py`. Risk manager + two-step confirm + journal logging.
- **Phase C — Self-improvement:** adaptive strategy weighting, event/time guards,
  per-provider accuracy weighting. Requires journal history.
- **Phase D — Backtest harness:** historical replay with walk-forward / out-of-sample
  split; per-strategy & per-preset performance reporting.

EOD report (summary + detailed, PAPER + LIVE, per-provider leaderboard) lands in Phase B,
enriched by C/D.

---

## 10. Risk & Safety (unchanged from build spec)

- Max ₹10,000 daily loss, max 1% account risk/trade, max 2 open positions (`.env`, ask before changing).
- Pre-trade check blocks + explains on violation; day P&L from live Dhan positions.
- PAPER/LIVE runtime toggle; orders mocked in PAPER, real in LIVE.
- Secrets only in `.env` (gitignored). SQLite local only. All currency in ₹.

---

## 11. Out of Scope

Multi-broker, multi-user/auth, cloud deploy, mobile, autonomous order firing,
guaranteed-accuracy claims. Anything new requires explicit approval.
