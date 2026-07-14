# Per-Run AI Cost Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture real token usage + rupee cost of every AI call and show today/month spend on Reports.

**Architecture:** Pure `services/cost.py` (pricing + JSONL ledger) plus a best-effort usage capture inside `providers.make_client` (non-breaking — `client(prompt)->str` unchanged). Reports gets an AI-cost readout. Mock mode stays free.

**Tech Stack:** Python stdlib (`json`, `datetime`), pytest, Streamlit.

**Reference spec:** [`docs/superpowers/specs/2026-07-14-ai-cost-tracking-design.md`](../specs/2026-07-14-ai-cost-tracking-design.md)

---

## Before You Start

- Branch `feature/ai-cost-tracking` (created). Repo-local git identity configured.
- Read `services/providers.py` (`make_client` anthropic + openai `call` closures — the SDK boundary), `services/audit.py` (the best-effort JSONL + module-global-path pattern to mirror), `pages/1_Reports.py`, `tests/conftest.py` (the autouse `_isolate_audit_ledger` fixture to extend).

---

## Task 1: cost.py + costs.json

**Files:**
- Create: `services/cost.py`
- Create: `costs.json`
- Test: `tests/test_cost.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cost.py`:
```python
from datetime import datetime, timezone, timedelta

from services import cost

IST = timezone(timedelta(hours=5, minutes=30))
_PRICES = {"default": {"input_per_1k": 0.0, "output_per_1k": 0.0},
           "m1": {"input_per_1k": 1.0, "output_per_1k": 2.0}}


def test_run_cost_listed_model():
    # 2000 in @1/1k + 1000 out @2/1k = 2.0 + 2.0 = 4.0
    assert cost.run_cost("m1", 2000, 1000, _PRICES) == 4.0


def test_run_cost_unknown_model_uses_default():
    assert cost.run_cost("unknown", 5000, 5000, _PRICES) == 0.0


def test_load_prices_reads_file(tmp_path):
    import json
    p = tmp_path / "costs.json"
    p.write_text(json.dumps({"default": {"input_per_1k": 0, "output_per_1k": 0},
                             "m1": {"input_per_1k": 3.0, "output_per_1k": 6.0}}))
    prices = cost.load_prices(path=p)
    assert prices["m1"]["input_per_1k"] == 3.0


def test_load_prices_missing_file_returns_empty(tmp_path):
    assert cost.load_prices(path=tmp_path / "nope.json") == {}


def test_log_and_read_runs_roundtrip(tmp_path):
    p = tmp_path / "cost.jsonl"
    cost.log_run("m1", 1000, 500, path=p, prices=_PRICES)
    cost.log_run("m1", 2000, 1000, path=p, prices=_PRICES)
    runs = cost.read_runs(path=p, limit=10)
    assert len(runs) == 2
    assert runs[0]["in"] == 2000            # newest first
    assert runs[0]["cost"] == 4.0
    assert "ts" in runs[0] and runs[0]["model"] == "m1"


def test_log_run_bad_path_swallowed():
    cost.log_run("m1", 1, 1, path="", prices=_PRICES)   # no raise


def test_summary_aggregates_by_model_and_period():
    runs = [
        {"ts": "2026-07-14T10:00:00+05:30", "model": "m1", "in": 1000, "out": 500, "cost": 2.0},
        {"ts": "2026-07-14T11:00:00+05:30", "model": "m2", "in": 2000, "out": 0, "cost": 2.0},
        {"ts": "2026-06-01T10:00:00+05:30", "model": "m1", "in": 500, "out": 0, "cost": 0.5},
    ]
    now = datetime(2026, 7, 14, 15, 0, tzinfo=IST)
    day = cost.summary(runs, period="day", now=now)
    assert day["total_cost"] == 4.0 and day["total_in"] == 3000
    assert day["by_model"]["m1"]["cost"] == 2.0
    all_ = cost.summary(runs, period="all", now=now)
    assert all_["total_cost"] == 4.5 and all_["n_runs"] == 3


def test_summary_empty_zeros():
    s = cost.summary([], period="all")
    assert s["total_cost"] == 0.0 and s["n_runs"] == 0 and s["by_model"] == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_cost.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `costs.json`**

```json
{
  "_comment": "AI provider prices in INR per 1000 tokens. EDITABLE. Update when a provider changes rates. Models not listed use 'default'.",
  "default": {"input_per_1k": 0.0, "output_per_1k": 0.0},
  "claude-sonnet-5": {"input_per_1k": 0.25, "output_per_1k": 1.25},
  "claude-haiku-4-5-20251001": {"input_per_1k": 0.07, "output_per_1k": 0.35}
}
```

- [ ] **Step 4: Write `services/cost.py`**

```python
"""Per-run AI cost tracking. Pure pricing math + a best-effort JSONL ledger of every
AI call's token usage and INR cost. Never raises (a cost-log failure must not block
signal generation). Path/prices resolve from module globals so they stay patchable."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

COST_PATH = "cost.jsonl"
COSTS_PATH = "costs.json"


def load_prices(path=None) -> dict:
    path = path if path is not None else COSTS_PATH
    try:
        p = Path(path)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                              # noqa: BLE001
        log.exception("cost load_prices failed")
        return {}


def run_cost(model: str, in_tok: int, out_tok: int, prices: dict) -> float:
    row = prices.get(model) or prices.get("default") or {}
    c = (in_tok / 1000.0) * float(row.get("input_per_1k", 0.0)) \
        + (out_tok / 1000.0) * float(row.get("output_per_1k", 0.0))
    return round(c, 4)


def log_run(model: str, in_tok: int, out_tok: int, *, path=None, prices=None) -> None:
    path = path if path is not None else COST_PATH
    try:
        prices = prices if prices is not None else load_prices()
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "model": model, "in": int(in_tok), "out": int(out_tok),
                           "cost": run_cost(model, in_tok, out_tok, prices)})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                              # noqa: BLE001 - never block signals
        log.exception("cost log_run failed")


def read_runs(path=None, limit: int = 500) -> list[dict]:
    path = path if path is not None else COST_PATH
    try:
        p = Path(path)
        if not p.exists():
            return []
        out = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return list(reversed(out))[:limit]
    except Exception:                              # noqa: BLE001
        log.exception("cost read_runs failed")
        return []


def summary(runs: list[dict], period: str = "all", now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()

    def _in_period(ts: str) -> bool:
        if period == "all":
            return True
        try:
            d = datetime.fromisoformat(ts).astimezone(now.tzinfo or timezone.utc).date()
        except (ValueError, TypeError):
            return False
        if period == "day":
            return d == today
        if period == "month":
            return d.year == today.year and d.month == today.month
        return True

    sel = [r for r in runs if _in_period(r.get("ts", ""))]
    by_model: dict[str, dict] = {}
    for r in sel:
        m = r.get("model", "?")
        b = by_model.setdefault(m, {"cost": 0.0, "in": 0, "out": 0, "n": 0})
        b["cost"] = round(b["cost"] + float(r.get("cost", 0)), 4)
        b["in"] += int(r.get("in", 0))
        b["out"] += int(r.get("out", 0))
        b["n"] += 1
    return {"total_cost": round(sum(r.get("cost", 0) for r in sel), 4),
            "total_in": sum(int(r.get("in", 0)) for r in sel),
            "total_out": sum(int(r.get("out", 0)) for r in sel),
            "n_runs": len(sel), "by_model": by_model}
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_cost.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add services/cost.py costs.json tests/test_cost.py
git commit -m "feat(cost): AI cost pricing + JSONL run ledger (pure, best-effort)"
```

---

## Task 2: Capture usage in make_client

**Files:**
- Modify: `services/providers.py`
- Test: `tests/test_providers_cost.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_providers_cost.py`:
```python
from services import providers, cost


class _Usage:
    def __init__(self, a, b, *, openai=False):
        if openai:
            self.prompt_tokens, self.completion_tokens = a, b
        else:
            self.input_tokens, self.output_tokens = a, b


class _AnthResp:
    def __init__(self):
        self.content = [type("C", (), {"text": "BUY"})()]
        self.usage = _Usage(1000, 500)


class _AnthSdk:
    def __init__(self, *a, **k):
        self.messages = self
    def create(self, **kw):
        return _AnthResp()


class _OpenAiResp:
    def __init__(self, with_usage=True):
        msg = type("M", (), {"content": "SELL"})()
        self.choices = [type("Ch", (), {"message": msg})()]
        self.usage = _Usage(2000, 800, openai=True) if with_usage else None


class _OpenAiSdk:
    def __init__(self, *a, with_usage=True, **k):
        self._wu = with_usage
        self.chat = self
        self.completions = self
    def create(self, **kw):
        return _OpenAiResp(self._wu)


def test_anthropic_client_logs_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost, "load_prices", lambda path=None: {
        "M": {"input_per_1k": 1.0, "output_per_1k": 2.0},
        "default": {"input_per_1k": 0.0, "output_per_1k": 0.0}})
    client = providers.make_client({"kind": "anthropic", "model": "M"}, "k",
                                   _anthropic_cls=_AnthSdk)
    text = client("prompt")
    assert text == "BUY"
    runs = cost.read_runs(path=str(tmp_path / "cost.jsonl"))
    assert len(runs) == 1 and runs[0]["in"] == 1000 and runs[0]["out"] == 500


def test_openai_client_logs_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost, "load_prices", lambda path=None: {
        "default": {"input_per_1k": 0.0, "output_per_1k": 0.0}})
    client = providers.make_client({"kind": "openai", "model": "M"}, "k",
                                   _openai_cls=_OpenAiSdk)
    assert client("prompt") == "SELL"
    runs = cost.read_runs(path=str(tmp_path / "cost.jsonl"))
    assert len(runs) == 1 and runs[0]["in"] == 2000 and runs[0]["out"] == 800


def test_missing_usage_skips_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))

    def _sdk(*a, **k):
        return _OpenAiSdk(with_usage=False)
    client = providers.make_client({"kind": "openai", "model": "M"}, "k",
                                   _openai_cls=_sdk)
    assert client("prompt") == "SELL"
    assert cost.read_runs(path=str(tmp_path / "cost.jsonl")) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_providers_cost.py -v`
Expected: FAIL — no cost logging in make_client yet.

- [ ] **Step 3: Edit `services/providers.py`**

Add `from services import cost` at the top, and a helper + wire it into both `call`
closures. Add this helper above `make_client`:
```python
def _log_usage(model: str, resp) -> None:
    """Best-effort: pull token usage off an SDK response and log the run cost.
    Never raises — a cost-log failure must not affect signal generation."""
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        in_tok = getattr(u, "input_tokens", None)
        if in_tok is None:
            in_tok = getattr(u, "prompt_tokens", 0)
        out_tok = getattr(u, "output_tokens", None)
        if out_tok is None:
            out_tok = getattr(u, "completion_tokens", 0)
        cost.log_run(model, int(in_tok or 0), int(out_tok or 0))
    except Exception:                              # noqa: BLE001
        pass
```
In the anthropic `call`:
```python
        def call(prompt: str) -> str:
            resp = sdk.messages.create(
                model=model, max_tokens=512,
                messages=[{"role": "user", "content": prompt}])
            _log_usage(model, resp)
            return resp.content[0].text
```
In the openai `call`:
```python
    def call(prompt: str) -> str:
        resp = sdk.chat.completions.create(
            model=model, max_tokens=512,
            messages=[{"role": "user", "content": prompt}])
        _log_usage(model, resp)
        return resp.choices[0].message.content
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_providers_cost.py tests/test_providers.py -v`
Expected: new 3 pass; existing `test_providers.py` still passes (its fake clients don't
go through make_client's SDK path, so they're unaffected).

- [ ] **Step 5: Commit**

```bash
git add services/providers.py tests/test_providers_cost.py
git commit -m "feat(cost): capture real token usage at the provider SDK boundary"
```

---

## Task 3: Reports section + test isolation + gitignore

**Files:**
- Modify: `pages/1_Reports.py`
- Modify: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Extend the autouse isolation fixture** in `tests/conftest.py` so cost
  runs also land in a temp file (mirrors the audit isolation):
```python
@pytest.fixture(autouse=True)
def _isolate_audit_ledger(tmp_path, monkeypatch):
    """confirm_and_place/prepare write audit events and make_client writes cost runs;
    point both ledgers at temp files so tests never create stray jsonl in the repo."""
    from services import audit, cost
    monkeypatch.setattr(audit, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))
    yield
```

- [ ] **Step 2: Add the Reports AI-cost section** — in `pages/1_Reports.py` add
  `from services import cost` (alongside the other service imports) and, near the bottom
  (e.g. before the audit-ledger expander), add:
```python
st.markdown("#### 💸 AI cost")
_runs = cost.read_runs()
_today = cost.summary(_runs, "day")
_month = cost.summary(_runs, "month")
if _runs:
    ac1, ac2 = st.columns(2)
    ac1.metric("Today", f"₹{_today['total_cost']:.2f}")
    ac2.metric("This month", f"₹{_month['total_cost']:.2f}")
    _rows = [{"model": m, "runs": b["n"], "in_tok": b["in"], "out_tok": b["out"],
              "₹": round(b["cost"], 2)} for m, b in _month["by_model"].items()]
    if _rows:
        st.dataframe(pd.DataFrame(_rows), use_container_width=True)
else:
    st.caption("No AI runs yet (mock mode is free).")
```

- [ ] **Step 3: Gitignore the runtime ledger** — append to `.gitignore`:
```
cost.jsonl
```

- [ ] **Step 4: Manual verification**

Run `streamlit run app.py`, open Reports: the "AI cost" section shows "No AI runs yet
(mock mode is free)." on a fresh ledger (default mock mode). (Real spend appears only
after `api` signal-source runs against real keys — not exercised here.) Parse-check the
page: `python -c "import ast; ast.parse(open('pages/1_Reports.py', encoding='utf-8').read())"`.

- [ ] **Step 5: Commit**

```bash
git add pages/1_Reports.py tests/conftest.py .gitignore
git commit -m "feat(cost): Reports AI-cost readout + test isolation + gitignore ledger"
```

---

## Task 4: Full-suite gate

- [ ] **Step 1:** `pytest tests/ -q` — all green (cost + provider-cost tests + every prior
  test; confirm existing provider/signal tests unaffected).
- [ ] **Step 2:** `streamlit run app.py` boots; Reports "AI cost" section renders; no
  traceback. Ensure no stray `cost.jsonl` in the repo root after (only the temp/data one).
  Fix + re-run if needed.

---

## Self-Review Notes

- **Spec coverage:** §2 modules → T1 (cost.py + costs.json), T2 (providers capture), T3
  (Reports + isolation + gitignore). §3 costs.json → T1. §4 cost.py API → T1. §5 boundary
  capture → T2 (both SDK shapes + missing-usage skip). §6 Reports → T3. §7 edges → default
  price, bad-path swallow, empty ledger caption, mock-free (T1/T2 tests + T3 caption). §8
  testing → T1–T2 unit; T3 manual.
- **No placeholders**; full code shown. **Non-breaking:** `client(prompt)->str` unchanged;
  `_log_usage` is a pure side-effect wrapper, so `call_provider`/`signal_engine` and their
  tests are untouched.
- **Type consistency:** `run_cost(model,in_tok,out_tok,prices)`, `log_run(...,*,path,prices)`,
  `read_runs(path,limit)`, `summary(runs,period,now)` identical across module, tests, page,
  and the `_log_usage` call; ledger keys (`ts,model,in,out,cost`) consistent everywhere.
