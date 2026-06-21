# Dhan-Claude Trader — Operating Guide & Live Walkthrough

A structured, tested procedure for running the software operationally — from cold
install to a live, human-confirmed trade and end-of-day review.

> **Golden rule:** AI recommends, *you* confirm every trade. No order fires without
> your second click. Start in PAPER, prove edge with the backtester, only then go LIVE.

Verified state at writing: **170 unit tests pass**, end-to-end demo runs, all 4 Streamlit
pages serve HTTP 200.

---

## 0. One-time setup (10 minutes)

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. create your private config from the template
cp .env.example .env            # Windows: copy .env.example .env
```

Edit `.env` and fill in:

| Key | Where to get it | Needed for |
|-----|-----------------|-----------|
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Dhan → Profile → DhanHQ API → Access Token | live data + orders |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `CEREBRAS_API_KEY` / `MISTRAL_API_KEY` | each provider's console | `api` signal mode only |
| `SIGNAL_SOURCE` | `mock` (free) or `api` (real LLMs) | signal generation |
| `TRADE_MODE` | `PAPER` or `LIVE` | order routing |
| `ACCOUNT_CAPITAL` | your paper capital, e.g. `100000` | PAPER position sizing |

`.env` is gitignored — your secrets never leave the machine.

**Verify the install before anything else:**
```bash
python -m pytest -q            # expect: 170 passed
python demo_end_to_end.py      # full pipeline, PAPER/mock, no creds needed
```
The demo prints every stage (regime → confluence → AI → quality → sizing → risk →
order → accounting → EOD) and writes a report to `reports/`. If it completes, the
engine is healthy.

---

## 1. Build your watchlist (one-time, then occasional)

`watchlist.json` lists what you trade. Each instrument needs a Dhan `security_id`.

- The app auto-resolves IDs from Dhan's scrip master on first run. To pre-check:
```bash
python scripts_check_strategies.py    # downloads master, resolves IDs, runs strategies
```
- If an index (NIFTY/BANKNIFTY) shows "unresolved", hand-fill its `security_id` in
  `watchlist.json` (index segment naming varies in Dhan's CSV).

Per-instrument fields: `symbol`, `exchange_segment` (`NSE_EQ`/`IDX_I`), `kind`
(`EQUITY`/`INDEX`/`FUT`/`OPT`), `lot_size`.

---

## 2. PROVE EDGE FIRST — backtest (do this before any real money)

This is non-negotiable. ~90% of F&O retail loses; the backtester is how you avoid
being in that group on a hunch.

```bash
python scripts_backtest.py
```

For each instrument it prints and writes `reports/backtest_<symbol>.md`:
- **Preset metrics** — in-sample vs **out-of-sample** (win%, net ₹, profit factor, max drawdown).
- **Top/Low strategies** + **PRUNE CANDIDATES** (negative out-of-sample expectancy → disable them).
- **Exit model A/B** — fixed stop/target vs **trailing**, with a verdict per instrument.

**How to read it:**
- If **out-of-sample** metrics collapse vs in-sample → the edge is overfit; don't trust it.
- Disable prune-candidate strategies in `strategies.json` presets.
- If trailing wins out-of-sample, note it (live trailing wiring is a follow-up step).

Only proceed to live signals on instruments/presets that hold up **out-of-sample**.

---

## 3. DAILY OPERATIONAL PROCEDURE

### 3.1 Launch (before market open, ~9:00 IST)
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`. Confirm the top banner shows **🟡 PAPER** (or 🔴 LIVE).
Pages (left sidebar): **Dashboard · Reports · Screener · Options**.

### 3.2 Morning Briefing — pick the day's strategy
On the Dashboard, open **🌅 Morning Briefing → Generate briefing**. It reads index
regime + India VIX + index RSI + event flags and recommends **one preset** with
reasoning and cautions. Example:
> ▶ Run preset: **range_scalper** — RANGING, VIX 22, RSI neutral. ⚠ Expiry day.

Set your active preset accordingly (in `watchlist.json`/`strategies.json` or just use it
as guidance). This replaces guessing.

### 3.3 Screen the universe
Open the **🔍 Screener** page → pick the preset → **Run scan**. It runs the 29 strategies
across your watchlist and lists which instruments currently have a signal, ranked by
confluence strength. Focus your attention on the top of that list.

### 3.4 Review a signal on the Dashboard
Each signal card shows:
- Consensus **BUY/SELL/HOLD**, confidence %, provider **agreement %**.
- **Quality score** (Tri-Factor): `PASS` (green) / `LOW` (amber) / `VETO` (red), with cautions.
- entry / SL / target, and per-provider chips.
- **📈 chart** expander — candles + EMA/Bollinger + RSI + MACD + entry/SL/target markers.

**Only act on `PASS` cards.** The Select button is disabled for `LOW`/`VETO`.

### 3.5 Place a trade — the two-step confirm (the safety core)
1. Click **Select <symbol> →**. The system computes the 1%-risk quantity, scales it by
   signal quality (confidence sizing), runs the **risk gate**, and opens a dialog.
2. The **Confirm dialog** shows full order details + risk-check result. **Review it.**
3. Click **✓ Place Order** — this is the *only* action that places an order. Or **Cancel**.

If the daily-loss limit (₹10,000) or max-positions (2) is breached, the risk panel turns
**🔴 BLOCKED** and new confirmations are disabled with the reason shown.

### 3.6 Monitor & exit
- **Open positions** panel (right) pulls live from Dhan with P&L.
- Click **Exit <symbol> ✕** to flatten (fires an opposite MARKET order; PAPER simulates).
- The risk monitor shows today's P&L, exposure %, and remaining loss buffer in real time.
- **Alert toasts** fire on fresh high-agreement signals (🔔) and risk breaches (🔴).

### 3.7 Options (optional, F&O)
Open the **⚙️ Options** page → choose underlying + bias + sell-delta → **Build spread**.
It constructs a defined-risk credit spread (bull-put / bear-call), shows **net credit,
max profit, max loss**, the legs, and a **payoff diagram**. Multi-leg placement is
**manual** in this build (leg-execution risk) — review max loss, then place legs yourself.

### 3.8 End of day — review & report
Open the **📊 Reports** page → pick the book (PAPER/LIVE):
- P&L account statement (gross → charges → net → unrealized → total), portfolio holdings,
  realized trades, journal stats (win rate, R:R predicted vs achieved).
- **📄 Generate EOD Report** → writes dated `reports/EOD_<date>_<mode>.md` + `.csv` with a
  **per-provider accuracy leaderboard**. Review which providers/strategies actually worked.

---

## 4. GOING LIVE (only after PAPER + backtest give you confidence)

1. In the Dashboard, switch **Trade mode → LIVE** (banner turns 🔴) and/or set
   `TRADE_MODE=LIVE` in `.env`.
2. Start with **tiny size** — verify one real order round-trips correctly (placed,
   appears in Dhan, logs to journal, shows in positions).
3. Confirm the live response shapes match: LTP parse, funds balance key, order IDs.
   (These are wrapped tolerantly but unverified against your live account until you do this.)
4. Keep the risk limits. Do not raise them to chase losses.

⚠️ **First live order is a verification exercise, not a profit attempt.** Watch it like a hawk.

---

## 5. WEEKLY / PERIODIC HYGIENE

- Re-run `python scripts_backtest.py` as new data accumulates; re-check prune candidates.
- Review EOD provider leaderboard trends — drop chronically wrong providers.
- Re-resolve the instrument master occasionally (delete `data/instrument_master.csv` to refetch).
- Reconcile charges in `charges.json` against your real Dhan contract notes.

---

## 6. TROUBLESHOOTING

| Symptom | Cause | Fix |
|---|---|---|
| Cards show "data error" / "insufficient candles" | No/placeholder Dhan creds, or unresolved security_id | Fill real `.env` creds; resolve IDs (§1) |
| "No resolved INDEX instrument" in briefing | NIFTY/BANKNIFTY security_id null | Hand-fill in `watchlist.json` |
| Quality always VETO | Event flag (e.g. RESULTS) or weak technicals | Check cautions; trade a cleaner setup |
| Signals don't change | 5-min cache | Click **⟳ Refresh** (clears cache) |
| AI mode returns HOLD/errors | Missing/invalid provider key | Check `.env` keys, or use `SIGNAL_SOURCE=mock` |
| Order "BLOCKED" | Risk gate (daily loss / max positions / >1% risk) | Expected — respect the limit |
| App won't start | Dependency/version | Re-run `pip install -r requirements.txt`; Python 3.13 |

---

## 7. SAFETY MODEL (what protects you)

1. **Two-step confirm** — `trade_controller.confirm_and_place` is the only order path; UI's
   second click is the only way to reach it. Proven by tests.
2. **Risk gate** — 1% per trade, ₹10k daily loss, 2 max positions; blocks + explains.
3. **Quality gate** — fundamentals/news as hard filters; low-quality signals can't be Selected.
4. **Defined-risk options** — credit spreads cap max loss.
5. **PAPER default** — full flow with simulated orders; flip to LIVE deliberately.
6. **Backtest + out-of-sample** — prove edge before risking capital; refuse curve-fitting.

---

## 8. HONEST LIMITS (read before risking money)

- **No "zero false signals", no profit guarantee.** This raises expected edge and enforces
  discipline; markets stay partly random.
- **Live response shapes unverified** until your first real run (LTP/funds/order parsing).
- **Charge rates & scrip columns are best-effort defaults** — verify against your account.
- **Trailing stop is backtest-only** so far; live trailing is a deliberate follow-up.
- **Options placement is manual** (no atomic multi-leg).
- The realistic edge is **~80% risk management, 20% signal.** The tool's job is to keep you
  in the disciplined minority — not to make markets beatable on demand.

---

## Quick command reference

```bash
pip install -r requirements.txt     # setup
python -m pytest -q                 # verify (170 passed)
python demo_end_to_end.py           # full pipeline demo (no creds)
python scripts_check_strategies.py  # live strategy check (needs creds)
python scripts_backtest.py          # backtest + prune + exit A/B (needs creds)
streamlit run app.py                # launch the dashboard
```
