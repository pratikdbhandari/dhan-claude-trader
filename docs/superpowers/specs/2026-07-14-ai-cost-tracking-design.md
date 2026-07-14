# Per-Run AI Cost Tracking Design

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `services/providers.py` (`make_client` — the real SDK boundary), `services/signal_engine`, `pages/1_Reports.py`.
**Origin:** Vibe-Trading review pick — per-run token + cost tracking so paid-LLM spend stays visible.

---

## 1. Purpose

Record the real token usage and rupee cost of every AI signal-generation call, and show
today/month spend on the Reports page. Accurate (captures the SDK's own `usage`), editable
pricing, non-breaking, and free in mock mode (no calls = ₹0).

**Principles:** capture usage at the provider boundary where it exists, before the text is
returned; pure cost math + a best-effort JSONL ledger (never blocks or crashes signal
generation); the `client(prompt) -> str` contract is unchanged.

**Out of scope:** budget caps / alerts, cost forecasting, non-AI costs (Dhan/brokerage —
already handled by the charges engine), per-signal attribution beyond per-call.

---

## 2. Modules / files

```
costs.json                NEW, editable: per-model ₹-per-1K-token input/output rates +
                            a "default" fallback.
services/cost.py          NEW: load_prices(path), run_cost(model, in_tok, out_tok, prices),
                            log_run(...) [append JSONL], read_runs(path, limit),
                            summary(runs, period) -> {total_cost, total_in, total_out,
                            by_model}. Best-effort I/O (never raises).
services/providers.py     CHANGE make_client: after each SDK call, read resp.usage and
                            cost.log_run(model, in_tok, out_tok); return text as before.
                            Best-effort — missing usage is skipped. client(prompt)->str
                            contract unchanged, so call_provider/signal_engine untouched.
pages/1_Reports.py        ADD "AI cost" section: today + month totals + per-model table.
tests/conftest.py         Extend the autouse isolation fixture to also point COST_PATH at
                            a temp file (like the audit ledger) so tests never write cost.jsonl.
.gitignore                ADD cost.jsonl (runtime ledger).
```

`COST_PATH = "cost.jsonl"`, `COSTS_PATH = "costs.json"` (relative — resolve in the working
dir next to trades.db / audit.jsonl, same convention).

---

## 3. costs.json

```json
{
  "_comment": "AI provider prices in INR per 1000 tokens. EDITABLE. Update when a provider changes rates.",
  "default": {"input_per_1k": 0.0, "output_per_1k": 0.0},
  "claude-sonnet-5": {"input_per_1k": 0.25, "output_per_1k": 1.25},
  "claude-haiku-4-5-20251001": {"input_per_1k": 0.07, "output_per_1k": 0.35}
}
```
(Illustrative rates — the user edits to their real per-model INR pricing. Any model not
listed uses `default`.)

## 4. cost.py

```python
COST_PATH = "cost.jsonl"
COSTS_PATH = "costs.json"

def load_prices(path=COSTS_PATH) -> dict:
    """Load costs.json; {} (=> all default 0) on missing/bad file."""

def run_cost(model: str, in_tok: int, out_tok: int, prices: dict) -> float:
    """INR cost = in/1000*input_per_1k + out/1000*output_per_1k, using the model's
    row or the 'default' row. Rounded to 4 dp."""

def log_run(model: str, in_tok: int, out_tok: int, *, path=None, prices=None) -> None:
    """Append one JSONL line {ts, model, in, out, cost}. Best-effort — never raises.
    prices default to load_prices(); path defaults to the COST_PATH module global."""

def read_runs(path=None, limit: int = 500) -> list[dict]:
    """Most-recent runs first; [] on any error. Resolves COST_PATH module global."""

def summary(runs: list[dict], period: str = "all", now=None) -> dict:
    """Filter runs to period ('day'|'month'|'all', by ts date) and aggregate:
    {total_cost, total_in, total_out, n_runs, by_model: {model: {cost, in, out, n}}}."""
```
`log_run`/`read_runs` resolve `COST_PATH` from the module global at call time (patchable,
same pattern the audit ledger uses).

## 5. Provider boundary capture (`services/providers.py`)

In `make_client`, wrap each SDK call so usage is logged then discarded from the return:
- Anthropic: `resp.usage.input_tokens`, `resp.usage.output_tokens`.
- OpenAI-compatible: `resp.usage.prompt_tokens`, `resp.usage.completion_tokens`.
Read via `getattr` defensively; if usage is absent/None, skip logging (no crash). Then
`return <text>` exactly as today. Because the returned type is still `str`, `call_provider`
and the signal pipeline are unchanged, and their tests keep passing.

## 6. Reports section (`pages/1_Reports.py`)

Add an "💸 AI cost" section: `runs = cost.read_runs()`;
`today = cost.summary(runs, "day")`, `month = cost.summary(runs, "month")`. Show two
metrics (today ₹, month ₹) + a per-model table (model, runs, in-tok, out-tok, ₹) from
`month["by_model"]`. Empty ledger → "No AI runs yet (mock mode is free)."

## 7. Error / edge handling

- Missing/None `resp.usage` → run not logged (no crash); the signal still returns.
- Unknown model → `default` price row (0 unless the user added it).
- Cost write/read failure → swallowed (logged), never blocks signal generation or a page.
- Empty ledger → friendly caption, no fake numbers.
- Mock signal source → no provider call → no cost rows (free path stays free).
- `cost.jsonl` gitignored + isolated in tests so runs never pollute the repo.

## 8. Testing

- `run_cost`: math for a listed model and for an unknown model (→ default); rounding.
- `load_prices`: returns rows from a temp costs.json; missing file → `{}`.
- `log_run`/`read_runs`: round-trip (newest first, respects limit); write to bad path
  swallowed.
- `summary`: aggregates total + `by_model`; `period="day"`/`"month"` filter by injected
  `now`; empty runs → zeros.
- `make_client` capture: a fake SDK whose response carries `.usage` triggers one
  `cost.log_run` (assert via a temp COST_PATH); a fake response without `.usage` logs
  nothing and still returns the text.
- Reports section verified by running.
