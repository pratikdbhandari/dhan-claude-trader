# Live Market, Trade Analysis & Global Linkage

Added 2026-07-16. Three feature waves that make the app live and concurrent with
the real market, all verified against live Dhan data during market hours.

## 1. Live market data (Dhan Data API)

**Pages:** `/live` (Live Market, in the sidebar), live ticker strip on the Dashboard.

- **Index ticker** — NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX with live
  LTP/change, refreshed every 5s, plus a market open/closed pill.
- **Live watchlist table** — LTP, change, %, O/H/L/prev-close for all
  [`watchlist.json`](../watchlist.json) instruments (5s).
- **Top gainers / losers** — computed live across the NIFTY-50 universe
  ([`universe.json`](../universe.json), security IDs verified against the Dhan
  instrument master), every 15s.
- **Live candlestick charts** — 54 symbols × 5m/15m/1h/daily, plotly, 60s
  refresh, closed-market hours removed from the axis.

### Rate-limit architecture (the part that matters)

Dhan throttles hard; naive per-instrument polling silently dies:

| API | Observed limit | Handling |
|---|---|---|
| marketfeed (ltp/ohlc/quote) | ~1 req/sec, batch ≤1000 instruments, error `805` | `services/market_feed.py` — ONE batched `ohlc_data` call covers ticker+watchlist+universe, 1.2s min gap, 3s TTL cache, serves stale while throttled |
| historical/intraday candles | empty responses (no error!) after ~4-5 rapid calls | `web/deps.py::fetch_candles` — per (instrument, interval) TTL cache (120s intraday / 600s daily), 0.35s spacing, serves stale on empty |

All UI polling hits these caches; the broker sees at most one marketfeed call
per TTL window regardless of how many browser tabs poll.

## 2. Trade analysis (`/analysis/{symbol}`)

`services/analysis.py` fuses everything into one structured verdict. Reachable
by clicking any screener row, mover, watchlist row, or the "Full analysis →"
link on a chart.

- **Verdict** — TAKE / CAUTION / AVOID / NO TRADE with a one-line reason.
  AVOID = quality-gate veto (e.g. stock-specific earnings imminent); CAUTION =
  news conflicts with signal or thin R:R.
- **Trade plan** — entry / SL / target / R:R and risk-sized qty.
- **Pros & cons** — real reasons from the 18 strategy votes, gate
  reasons/cautions, RSI extremes, regime, provider agreement, news flow and
  global cues.
- **News impact** — RSS headlines (Moneycontrol + ET) matched to the share via
  alias map, split positive/negative/neutral by keyword sentiment; net direction
  feeds the verdict. Market-wide headlines shown as context.
- **Corporate events** — stock headlines bucketed into ORDERS · RESULTS ·
  MANAGEMENT · PLEDGE · HOLDING CHANGE · REGULATORY · CORP ACTION.
- **Fundamentals & shareholding** — P/E, EPS, market cap, promoter holding
  (`heldPercentInsiders`) and institutional holding via Yahoo Finance.
- **Indicators + votes** — RSI/ADX/ATR/MACD/EMAs, full vote table, category
  score bars.

Charts on `/live` overlay the same signal on the charted timeframe: EMA20/50,
dotted entry/SL/target lines, BUY/SELL badge.

The screener (`/screener`) scans watchlist or full NIFTY-50, optional
"setups only" filter; rows click through to the analysis page.

## 3. World-market linkage (`services/global_markets.py`)

Sector → global-driver map answers "which world markets move this share, and
which way":

| Sector | Drivers (sign) |
|---|---|
| IT | NASDAQ (+), S&P 500 (+), USD/INR (+ weaker rupee helps) |
| Banks / Financials | US 10Y (−), Dollar index (−), S&P (+) |
| Metals | Shanghai (+), Hang Seng (+), Dollar index (−) |
| Oil | Brent: ONGC (+ upstream), BPCL (− refiner), RELIANCE mixed |
| Autos | Brent (−), Nikkei (+), S&P (+) |
| Pharma | USD/INR (+), S&P (+) |
| Consumer | Gold (+ Titan), S&P (+) |
| Indices | S&P (+), Nikkei (+), Hang Seng (+), Dollar (−), Brent (−), US10Y (−) |

- Live world prices via yfinance (14 tickers: US/Europe/Asia indices, USD/INR,
  Dollar index, Brent, Gold, US 10Y), 10-min cache.
- **Global sentiment** RISK-ON/RISK-OFF/MIXED on the Live page.
- **FII/DII daily cash flows** from NSE's (unofficial) `fiidiiTradeReact`
  endpoint — cookie warm-up + browser UA, 30-min cache, degrades to empty.
- Per-stock **net global cue** (SUPPORTIVE/AGAINST/NEUTRAL) is shown as a
  driver table on the analysis page and folded into the pros/cons.

## Data-source honesty

- News sentiment is keyword-based — a flag, not a substitute for reading.
- Pledge %, quarterly promoter/FII/DII *changes*: no reliable free API; covered
  as news events + current holding levels. Wire NSE filings/Trendlyne/screener.in
  if exact tables are needed.
- Yahoo world data can be ~15 min delayed on some exchanges.
- `websockets>=13` is required — older pins break `yfinance` imports.
- A verdict measures setup quality, not a profit guarantee. Every order still
  goes through explicit user confirmation on the Dashboard.

## Verification

- 420 tests pass (`python -m pytest tests/`), including offline unit tests for
  the feed cache/throttle, analysis verdicts, event classification, driver math.
- Verified live in-browser: rates ticking, movers, chart overlays, TCS = TAKE
  with promoter 71.8% / institutions 17.5%, FII/DII flows matching NSE.
- Paper trade placed end-to-end (SELL RELIANCE ×85, journaled `PLACED`).
