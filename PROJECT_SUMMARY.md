# Dhan-Claude Trader — Project Summary

A local, single-operator desktop trading assistant. It pulls market data from **Dhan**,
generates AI trade signals from multiple LLM providers over a 29-strategy technical
confluence, and places orders on Dhan **only after an explicit two-step human
confirmation**. Built as a production-quality local MVP (not a multi-tenant SaaS).

> **Philosophy:** AI prepares and recommends; the human confirms every trade. No order
> ever fires autonomously. There is no "zero false signals" — confluence + AI judgment +
> the manual confirm reduce, but never eliminate, losing trades.

---

## Status

- **All phases complete.** 112 unit tests green. Multipage Streamlit app boots (HTTP 200).
- Local git only (master + merged phase branches). Not yet pushed to a remote.
- Verified offline: tests, app boot, `DhanClient` offline construction, no-auto-fire guarantee.

---

## How to run

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in real values
streamlit run app.py
```

Default **PAPER + mock** mode runs the entire flow free (no API keys, no real orders).
Flip to `api` signal source and/or `LIVE` trade mode from the UI when ready.

### Required `.env` values
| Key | Purpose |
|-----|---------|
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Dhan broker (market data + orders) |
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `MISTRAL_API_KEY` | AI providers (only for `api` mode; blank = provider off) |
| `SIGNAL_SOURCE` | `mock` (free, deterministic) or `api` (real LLMs) |
| `TRADE_MODE` | `PAPER` (simulated) or `LIVE` (real Dhan orders) |
| `MAX_DAILY_LOSS`=10000, `MAX_RISK_PER_TRADE_PCT`=1.0, `MAX_OPEN_POSITIONS`=2 | risk limits |
| `ACCOUNT_CAPITAL`=100000 | paper-mode capital for 1% position sizing |

Secrets live **only** in `.env` (gitignored). Never committed.

---

## Architecture (layered, local-first)

```
Presentation   app.py · pages/1_Reports.py            (thin Streamlit, manual-verified)
Application    signal_engine · risk_manager · trade_controller · eod_report
Domain         strategies/* · regime · accounting · charges · providers · prompt
Integration    dhan_client · journal · instruments · news · fundamentals
Data/External  Dhan API · Anthropic/Groq/Cerebras/Mistral · yfinance · RSS · SQLite
```

All business logic lives in plain, unit-tested functions; `app.py`/pages only render.
The **no-auto-fire guarantee** lives in `trade_controller` (prepare and confirm are
separate calls; an order can only be placed by `confirm_and_place`, reached solely from
the confirm dialog's second click).

---

## Build phases

| Phase | Modules | What it delivers |
|-------|---------|------------------|
| **A** | `core/models`, `services/indicators`, `regime`, `strategies/*`, `strategies/engine`, `accounting`, `charges` | 29 selectable technical strategies, ADX/ATR regime gate, category-weighted (decorrelated) confluence, Indian charge calculator, FIFO realized P&L, portfolio, P&L statement |
| **B1** | `dhan_client` (extended), `data/journal`, `data/segments` | LTP, candles (5/15/day), holdings, modify/cancel/exit (opposite MARKET), bracket order; SQLite journal (log/list/stats/to_legs) bridging to accounting |
| **B2** | `news`, `fundamentals`, `prompt`, `providers`, `signal_engine` | RSS news, yfinance fundamentals, concurrent multi-provider fan-out, strict-JSON parse→retry→HOLD, simple consensus, deterministic mock mode, 5-min cache |
| **B3** | `risk_manager`, `trade_controller`, `app.py` | pre-trade gate (₹10k loss / 1% per trade / 2 open), two-step confirm state machine, full dashboard (signal cards, confirm dialog, risk panel, positions + one-click exit, auto-refresh) |
| **B4** | `instruments`, `eod_report`, `pages/1_Reports.py` | Dhan scrip-master resolver (symbol→security_id), EOD report (summary + per-provider accuracy leaderboard + md/csv), accounting/reports UI page |

---

## The 29-strategy catalog

- **Trend (1–9):** EMA cross, EMA ribbon, MACD cross, MACD histogram, ADX/DI, Supertrend, PSAR, price vs 200EMA, market structure.
- **Mean-reversion (10–17):** RSI extremes, RSI divergence, Bollinger reversal, Stochastic, Williams %R, CCI, VWAP reversion, z-score.
- **Breakout (18–23):** BB squeeze, Donchian, Opening Range, ATR expansion, prev-day break, Keltner.
- **Volume (24–27):** volume spike, OBV trend, VWAP cross, volume-weighted breakout.
- **Structure (28–29):** multi-timeframe alignment, pivot S/R.

Preset bundles in `strategies.json`: intraday_momentum, range_scalper, positional_quality, all_on. Regime gate disables strategies that don't fit the current market; confluence is weighted by **category** (so nine correlated trend indicators don't fake conviction).

---

## Signal pipeline

```
Dhan candles → regime classify → eligible strategies vote → category-weighted confluence
            → assemble context (news, fundamentals, indicators, position)
            → build prompt → fan out to enabled providers (concurrent)
            → each: strict JSON → validate → retry once → HOLD fallback
            → consensus (majority, avg confidence, agreement%)
            → RISK GATE → TWO-STEP HUMAN CONFIRM → place order → journal
            → accounting + EOD report read journal
```

---

## Accounting & charges

- **Indian charges** (`charges.json`, editable): brokerage, STT, exchange txn, SEBI, stamp, GST — per segment (equity delivery/intraday, futures, options). Hybrid: formula default, reconcile with Dhan actuals for live trades.
- **FIFO realized P&L** (long + short), weighted-avg portfolio with injected LTP for unrealized, P&L account statement, charges ledger. Separate PAPER/LIVE books.
- Worked example proven by tests: delivery buy 10@100 → ₹1.19 charges; round-trip 100→110 → net ₹97.67 after charges.

---

## Test coverage (112 tests)

Strategies, indicators, regime, confluence engine, charges, accounting (FIFO/short/portfolio/statement), dhan_client (data + orders, dry-run), journal, segments, news, fundamentals, prompt, providers (parse/retry/factory), signal_engine (mock/consensus/cache), risk_manager (every block reason), trade_controller (no-auto-fire), instruments, eod_report. UI (`app.py`, pages) verified by running, not unit-tested.

---

## Honest caveats (read before risking money)

- **No backtest yet.** Strategy params are reasoned defaults, untuned. A backtest harness (Phase D) is the real validation step before trusting signals with capital. Guard against curve-fitting (out-of-sample / walk-forward).
- **Live API shapes unverified.** Provider call shapes, Dhan `ticker_data` LTP parse, funds balance key, and scrip-master column names are wrapped tolerantly but not hit with real keys yet — verify on first live run.
- **Charge rates are defaults** — verify against your Dhan contract note; edit `charges.json` freely (not a risk-limit default).
- **AI needs paid API.** The Anthropic/Groq/etc. APIs are billed separately from any Claude subscription; mock mode is the free harness.
- **No "zero false signals."** Markets are partly random; this maximizes expected edge and robustness, not certainty.

---

## Out of scope (deliberately not built)

Multi-broker, multi-user/auth, cloud deploy, mobile, autonomous order firing, scheduled
auto-EOD, tax/ITR export, accuracy-weighted consensus + event guards (Phase C),
backtest harness (Phase D).

---

## Repo layout

```
app.py                      Streamlit dashboard
pages/1_Reports.py          accounting + EOD report page
core/                       models, config
services/                   strategies/, indicators, regime, accounting, charges,
                            dhan_client, news, fundamentals, prompt, providers,
                            signal_engine, risk_manager, trade_controller,
                            instruments, eod_report
data/                       journal (SQLite), segments
strategies.json             29-strategy registry + presets
providers.json              AI provider registry
charges.json                Indian charge rates
watchlist.json              instruments to watch
docs/superpowers/specs/     design specs (per phase)
docs/superpowers/plans/     TDD implementation plans (per phase)
tests/                      112 pytest tests
```

---

*Built with a brainstorm → spec → plan → TDD-build → verify → merge cycle for each
slice. Specs and plans are preserved under `docs/superpowers/`.*
