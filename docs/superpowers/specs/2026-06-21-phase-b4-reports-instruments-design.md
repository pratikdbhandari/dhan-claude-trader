# Phase B4 — Reports + Instruments Design

**Date:** 2026-06-21
**Status:** Approved
**Depends on:** journal, accounting, signal models (consensus_json)

---

## 1. Purpose

Final slice: an instrument-master resolver (symbol → Dhan security_id), an end-of-day
report (summary + per-provider accuracy leaderboard + detailed trades, PAPER & LIVE),
and a Streamlit Reports page exposing accounting views + the report button.

---

## 2. instruments.py (`services/instruments.py`)

- Dhan scrip CSV: `https://images.dhan.co/api-data/api-scrip-master.csv` (compact).
- `download_master(fetch=None, path="data/instrument_master.csv") -> str` — fetch +
  cache to disk; `fetch(url)->str` injectable.
- `build_index(csv_text) -> dict[(symbol, exchange_segment), security_id]` — parse CSV
  (csv.DictReader). Map uses the trading symbol + segment columns; tolerant to column
  naming (looks for SEM_TRADING_SYMBOL / SYMBOL_NAME and SEM_SMST_SECURITY_ID variants).
- `resolve(instrument, index) -> Instrument` — returns a copy with security_id filled if
  found in index, else unchanged (security_id stays None).
- `resolve_watchlist(instruments, index) -> list[Instrument]`.

Failure (network/parse) → empty index, instruments unresolved (logged, no crash).

---

## 3. eod_report.py (`services/eod_report.py`)

- `build_report(journal_conn, mode, date_key=None, ltp_fn=None) -> dict`:
  - `summary`: from journal.stats(mode) + accounting.pnl_statement over journal legs →
    `{trades, wins, win_rate, net_pnl, avg_rr_predicted, avg_rr_achieved}`.
  - `leaderboard`: parse each closed trade's `consensus_json` → provider signals.
    Winning direction = trade `side` if pnl>0 else opposite. A provider is *correct* if
    its signal == winning direction (HOLD excluded). Per provider:
    `{provider, calls, correct, accuracy}`.
  - `detailed`: list of closed trades (symbol, side, qty, entry/exit, pnl, rr_predicted,
    rr_achieved, consensus, providers).
- `write_report(report, out_dir="reports", date_key) -> (md_path, csv_path)`:
  - `EOD_<date>.md` — summary table + leaderboard.
  - `EOD_<date>.csv` — detailed trades.
  Both written for the given mode; filename includes mode (e.g. `EOD_2026-06-21_PAPER.md`).

Empty journal → zeroed summary, empty leaderboard/detailed, files still written.

---

## 4. pages/1_Reports.py (Streamlit multipage)

Sits beside app.py (`pages/` auto-detected). Renders:
- Book toggle PAPER/LIVE.
- Accounting: portfolio holdings, realized trades, P&L account statement, charges
  ledger (from accounting over journal.to_legs).
- Journal stats (win rate, avg R:R predicted vs achieved).
- "Generate EOD Report" button → build_report + write_report, render on-screen + show
  saved file paths.
Manual-verified (not unit-tested).

---

## 5. Data Flow

```
Dhan scrip CSV → instruments.build_index → resolve_watchlist → security_ids
journal trades (+ consensus_json) → eod_report.build_report
   ├─ accounting.pnl_statement / journal.stats → summary
   ├─ parse consensus_json → per-provider leaderboard
   └─ closed trades → detailed
   → write_report → reports/EOD_<date>_<mode>.{md,csv} + UI
```

---

## 6. Error / Edge Handling

- CSV download fail → empty index; watchlist stays unresolved; app shows "unresolved".
- Malformed consensus_json → that trade skipped in leaderboard (logged).
- Trade with pnl=0 → excluded from leaderboard winning-direction (neutral).
- Empty book → zeroed report, files still written.

---

## 7. Testing (TDD; page manual)

- `instruments`: fake CSV text → build_index → resolve fills security_id; unknown
  symbol → unchanged; network error → empty index.
- `eod_report`: temp journal with closed trades carrying consensus_json → summary
  numbers, leaderboard accuracy per provider, detailed rows; write_report creates md+csv
  with expected content; empty journal → zeroed but files written.

---

## 8. Out of Scope

Scheduled/auto EOD at market close (manual button only). Tax export. Multi-day
aggregation beyond the date filter. Live-key verification.
