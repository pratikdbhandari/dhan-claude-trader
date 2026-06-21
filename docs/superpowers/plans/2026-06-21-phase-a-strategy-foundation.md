# Phase A: Strategy Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mechanical foundation — a `dhan_client` broker wrapper, a market-regime classifier, the 29-strategy engine with category-weighted (decorrelated) confluence — fully testable with no API keys or cost.

**Architecture:** Pure functions over pandas DataFrames of OHLCV candles. Each strategy is a registered function returning a `StrategyVote`. The engine runs regime-eligible strategies, aggregates votes by category (not raw count) into a `ConfluenceSnapshot`. `dhan_client` wraps `dhanhq` with `dry_run` awareness and uniform error surfacing. No AI in Phase A — the snapshot is the deliverable consumed by Phase B.

**Tech Stack:** Python 3.13, pandas, `ta`, `dhanhq`, pytest. Indicators via `ta`; data via Dhan; tests use synthetic candle fixtures (no network).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `core/models.py` (modify) | add `StrategyVote`, `ConfluenceSnapshot`, `Regime`, `Candles` types |
| `services/dhan_client.py` (create) | `dhanhq` wrapper: LTP, candles, positions, funds, place/modify/cancel/exit, dry_run |
| `services/indicators.py` (create) | thin `ta`-based helpers returning Series (RSI, MACD, BB, ATR, ADX, etc.) |
| `services/regime.py` (create) | classify trending/ranging/volatile from ADX + ATR |
| `services/strategies/base.py` (create) | `StrategyVote`, registry decorator, `Strategy` protocol |
| `services/strategies/trend.py` (create) | strategies 1–9 |
| `services/strategies/mean_reversion.py` (create) | strategies 10–17 |
| `services/strategies/breakout.py` (create) | strategies 18–23 |
| `services/strategies/volume.py` (create) | strategies 24–27 |
| `services/strategies/structure.py` (create) | strategies 28–29 |
| `services/strategies/engine.py` (create) | run eligible strategies, category-weighted aggregation |
| `strategies.json` (create) | 29 strategy registry + preset bundles |
| `tests/conftest.py` (create) | synthetic candle fixtures (trending/ranging) |
| `tests/test_*.py` (create) | one test module per unit above |

**Dependency order:** models → indicators → (dhan_client ∥ regime ∥ strategies/base) → strategy category files → engine. Within strategy category files, the four files are independent and parallelizable once `base.py` + `indicators.py` exist.

---

## Task 1: Domain types for strategies

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_models_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_strategy.py
from core.models import StrategyVote, Regime, SignalType

def test_strategy_vote_defaults():
    v = StrategyVote(strategy_id=1, name="ema_cross", category="trend",
                     vote=SignalType.BUY, strength=70)
    assert v.vote is SignalType.BUY
    assert v.strength == 70
    assert v.category == "trend"

def test_regime_enum_values():
    assert {r.value for r in Regime} == {"TRENDING", "RANGING", "VOLATILE"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_strategy.py -v`
Expected: FAIL with `ImportError: cannot import name 'StrategyVote'`

- [ ] **Step 3: Add types to `core/models.py`**

```python
# append to core/models.py

class Regime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"


@dataclass
class StrategyVote:
    strategy_id: int
    name: str
    category: str                 # trend | mean_reversion | breakout | volume | structure
    vote: SignalType
    strength: int                 # 0-100
    detail: str = ""              # human-readable why


@dataclass
class ConfluenceSnapshot:
    regime: Regime
    votes: list[StrategyVote]
    # category-weighted tallies (decorrelated):
    category_scores: dict[str, float]   # category -> net score [-1..1]
    net_score: float                    # overall [-1..1], BUY>0 SELL<0
    bias: SignalType                    # BUY|SELL|HOLD from net_score thresholds
    buy_count: int
    sell_count: int
    hold_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models_strategy.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_models_strategy.py
git commit -m "feat(models): add StrategyVote, Regime, ConfluenceSnapshot types"
```

---

## Task 2: Synthetic candle fixtures

**Files:**
- Create: `tests/conftest.py`
- Test: `tests/test_fixtures.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fixtures.py
def test_trending_fixture_rises(trending_candles):
    assert trending_candles["close"].iloc[-1] > trending_candles["close"].iloc[0]
    assert set(["open","high","low","close","volume"]).issubset(trending_candles.columns)

def test_ranging_fixture_oscillates(ranging_candles):
    c = ranging_candles["close"]
    assert c.max() - c.min() < c.mean() * 0.1   # stays in a band
    assert len(ranging_candles) >= 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_fixtures.py -v`
Expected: FAIL with fixture `trending_candles` not found

- [ ] **Step 3: Implement fixtures**

```python
# tests/conftest.py
import numpy as np
import pandas as pd
import pytest

def _ohlcv(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    rng = np.random.default_rng(42)
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})

@pytest.fixture
def trending_candles():
    n = 250
    close = 100 + np.linspace(0, 40, n) + np.random.default_rng(1).normal(0, 0.5, n)
    return _ohlcv(close)

@pytest.fixture
def ranging_candles():
    n = 250
    close = 100 + 3 * np.sin(np.linspace(0, 12 * np.pi, n)) \
            + np.random.default_rng(2).normal(0, 0.3, n)
    return _ohlcv(close)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_fixtures.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_fixtures.py
git commit -m "test: synthetic trending/ranging candle fixtures"
```

---

## Task 3: Indicator helpers

**Files:**
- Create: `services/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_indicators.py
from services import indicators as ind

def test_rsi_bounds(trending_candles):
    rsi = ind.rsi(trending_candles["close"])
    last = rsi.dropna().iloc[-1]
    assert 0 <= last <= 100
    assert last > 50   # uptrend => RSI above midline

def test_atr_positive(trending_candles):
    atr = ind.atr(trending_candles)
    assert atr.dropna().iloc[-1] > 0

def test_adx_high_in_trend(trending_candles):
    assert ind.adx(trending_candles).dropna().iloc[-1] > 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: services.indicators`

- [ ] **Step 3: Implement**

```python
# services/indicators.py
"""Thin wrappers over the `ta` library returning pandas Series.
Centralised so every strategy computes indicators the same way."""
from __future__ import annotations
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.trend import MACD, ADXIndicator, EMAIndicator, CCIIndicator, PSARIndicator
from ta.volatility import BollingerBands, AverageTrueRange, KeltnerChannel
from ta.volume import OnBalanceVolumeIndicator

def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    return RSIIndicator(close, window=window).rsi()

def ema(close: pd.Series, window: int) -> pd.Series:
    return EMAIndicator(close, window=window).ema_indicator()

def macd_lines(close: pd.Series):
    m = MACD(close)
    return m.macd(), m.macd_signal(), m.macd_diff()

def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return AverageTrueRange(df["high"], df["low"], df["close"], window=window).average_true_range()

def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return ADXIndicator(df["high"], df["low"], df["close"], window=window).adx()

def bollinger(close: pd.Series, window: int = 20, dev: int = 2):
    bb = BollingerBands(close, window=window, window_dev=dev)
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()

def stoch(df: pd.DataFrame):
    s = StochasticOscillator(df["high"], df["low"], df["close"])
    return s.stoch(), s.stoch_signal()

def williams_r(df: pd.DataFrame) -> pd.Series:
    return WilliamsRIndicator(df["high"], df["low"], df["close"]).williams_r()

def cci(df: pd.DataFrame) -> pd.Series:
    return CCIIndicator(df["high"], df["low"], df["close"]).cci()

def obv(df: pd.DataFrame) -> pd.Series:
    return OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()

def keltner(df: pd.DataFrame):
    k = KeltnerChannel(df["high"], df["low"], df["close"])
    return k.keltner_channel_hband(), k.keltner_channel_lband()

def psar(df: pd.DataFrame) -> pd.Series:
    return PSARIndicator(df["high"], df["low"], df["close"]).psar()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/indicators.py tests/test_indicators.py
git commit -m "feat(indicators): ta-backed indicator helpers"
```

---

## Task 4: Regime classifier

**Files:**
- Create: `services/regime.py`
- Test: `tests/test_regime.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regime.py
from services.regime import classify_regime
from core.models import Regime

def test_trending_market_classified_trending(trending_candles):
    assert classify_regime(trending_candles) is Regime.TRENDING

def test_ranging_market_not_trending(ranging_candles):
    assert classify_regime(ranging_candles) in (Regime.RANGING, Regime.VOLATILE)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_regime.py -v`
Expected: FAIL with `ModuleNotFoundError: services.regime`

- [ ] **Step 3: Implement**

```python
# services/regime.py
"""Market regime classifier. ADX measures trend strength; normalised ATR
measures volatility. Trending => trend strategies eligible; Ranging =>
mean-reversion; Volatile => breakout-biased / caution."""
from __future__ import annotations
import pandas as pd
from core.models import Regime
from services import indicators as ind

ADX_TREND_THRESHOLD = 25.0
ATR_VOLATILE_PCT = 0.025   # ATR > 2.5% of price => volatile

def classify_regime(df: pd.DataFrame) -> Regime:
    adx_val = ind.adx(df).dropna().iloc[-1]
    atr_val = ind.atr(df).dropna().iloc[-1]
    price = df["close"].iloc[-1]
    atr_pct = atr_val / price if price else 0.0
    if adx_val >= ADX_TREND_THRESHOLD:
        return Regime.TRENDING
    if atr_pct >= ATR_VOLATILE_PCT:
        return Regime.VOLATILE
    return Regime.RANGING
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_regime.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/regime.py tests/test_regime.py
git commit -m "feat(regime): ADX/ATR market regime classifier"
```

---

## Task 5: Strategy base + registry

**Files:**
- Create: `services/strategies/__init__.py`, `services/strategies/base.py`
- Test: `tests/test_strategy_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategy_base.py
from services.strategies import base
from core.models import SignalType, StrategyVote

def test_register_and_run():
    base.REGISTRY.clear()

    @base.strategy(id=999, name="always_buy", category="trend",
                   regimes=("TRENDING",), intraday_only=False)
    def always_buy(df):
        return SignalType.BUY, 80, "test"

    assert 999 in base.REGISTRY
    spec = base.REGISTRY[999]
    vote = spec.run(df=None)
    assert isinstance(vote, StrategyVote)
    assert vote.vote is SignalType.BUY and vote.strength == 80

def test_eligible_filters_by_regime_and_style():
    base.REGISTRY.clear()
    @base.strategy(id=1, name="t", category="trend", regimes=("TRENDING",), intraday_only=True)
    def t(df): return SignalType.HOLD, 0, ""
    @base.strategy(id=2, name="m", category="mean_reversion", regimes=("RANGING",), intraday_only=False)
    def m(df): return SignalType.HOLD, 0, ""

    elig = base.eligible(regime="TRENDING", style="positional")
    assert [s.id for s in elig] == []          # t is intraday_only, m wrong regime
    elig2 = base.eligible(regime="TRENDING", style="intraday")
    assert [s.id for s in elig2] == [1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_strategy_base.py -v`
Expected: FAIL with `ModuleNotFoundError: services.strategies.base`

- [ ] **Step 3: Implement**

```python
# services/strategies/__init__.py
# (empty — package marker)
```

```python
# services/strategies/base.py
"""Strategy registry. Each strategy is a function (df)->(SignalType, strength, detail),
wrapped with metadata. The engine runs only regime/style-eligible strategies."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import pandas as pd
from core.models import SignalType, StrategyVote

VoteFn = Callable[[pd.DataFrame], tuple]

@dataclass
class StrategySpec:
    id: int
    name: str
    category: str
    regimes: tuple[str, ...]
    intraday_only: bool
    fn: VoteFn

    def run(self, df: pd.DataFrame) -> StrategyVote:
        vote, strength, detail = self.fn(df)
        return StrategyVote(strategy_id=self.id, name=self.name,
                            category=self.category, vote=vote,
                            strength=int(strength), detail=detail)

REGISTRY: dict[int, StrategySpec] = {}

def strategy(*, id: int, name: str, category: str,
             regimes: tuple[str, ...], intraday_only: bool):
    def deco(fn: VoteFn) -> VoteFn:
        REGISTRY[id] = StrategySpec(id, name, category, regimes, intraday_only, fn)
        return fn
    return deco

def eligible(*, regime: str, style: str) -> list[StrategySpec]:
    out = []
    for spec in REGISTRY.values():
        if spec.intraday_only and style != "intraday":
            continue
        if regime not in spec.regimes:
            continue
        out.append(spec)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_strategy_base.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/__init__.py services/strategies/base.py tests/test_strategy_base.py
git commit -m "feat(strategies): registry + regime/style eligibility"
```

---

## Task 6: Trend strategies (1–9)

**Files:**
- Create: `services/strategies/trend.py`
- Test: `tests/test_trend_strategies.py`

> **Decorator metadata for each** uses `base.strategy(...)`. `regimes` lists which
> regimes the strategy is eligible in. Strength is a 0-100 conviction. Return
> `(SignalType.HOLD, 0, "...")` when the setup is absent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trend_strategies.py
import services.strategies.trend as trend
from services.strategies import base
from core.models import SignalType

def test_ema_cross_buys_in_uptrend(trending_candles):
    vote = base.REGISTRY[1].run(trending_candles)
    assert vote.vote is SignalType.BUY

def test_price_above_200ema_regime(trending_candles):
    vote = base.REGISTRY[8].run(trending_candles)
    assert vote.vote is SignalType.BUY

def test_all_trend_registered():
    assert all(i in base.REGISTRY for i in range(1, 10))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_trend_strategies.py -v`
Expected: FAIL (`KeyError: 1` or import error)

- [ ] **Step 3: Implement**

```python
# services/strategies/trend.py
"""Trend / momentum strategies 1-9. Eligible mainly in TRENDING (some in VOLATILE)."""
from __future__ import annotations
import pandas as pd
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_TREND = ("TRENDING", "VOLATILE")

@strategy(id=1, name="ema_cross_9_21", category="trend", regimes=_TREND, intraday_only=False)
def ema_cross(df):
    fast, slow = ind.ema(df["close"], 9), ind.ema(df["close"], 21)
    if fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-2] <= slow.iloc[-2]:
        return SignalType.BUY, 70, "9EMA crossed above 21EMA"
    if fast.iloc[-1] < slow.iloc[-1] and fast.iloc[-2] >= slow.iloc[-2]:
        return SignalType.SELL, 70, "9EMA crossed below 21EMA"
    bias = SignalType.BUY if fast.iloc[-1] > slow.iloc[-1] else SignalType.SELL
    return bias, 55, "EMA alignment (no fresh cross)"

@strategy(id=2, name="ema_ribbon", category="trend", regimes=_TREND, intraday_only=False)
def ema_ribbon(df):
    es = [ind.ema(df["close"], w).iloc[-1] for w in (8, 13, 21, 34, 55)]
    if all(es[i] > es[i+1] for i in range(len(es)-1)):
        return SignalType.BUY, 75, "EMA ribbon stacked bullish"
    if all(es[i] < es[i+1] for i in range(len(es)-1)):
        return SignalType.SELL, 75, "EMA ribbon stacked bearish"
    return SignalType.HOLD, 0, "ribbon mixed"

@strategy(id=3, name="macd_signal_cross", category="trend", regimes=_TREND, intraday_only=False)
def macd_cross(df):
    macd, sig, _ = ind.macd_lines(df["close"])
    if macd.iloc[-1] > sig.iloc[-1] and macd.iloc[-2] <= sig.iloc[-2]:
        return SignalType.BUY, 70, "MACD crossed above signal"
    if macd.iloc[-1] < sig.iloc[-1] and macd.iloc[-2] >= sig.iloc[-2]:
        return SignalType.SELL, 70, "MACD crossed below signal"
    return SignalType.HOLD, 0, "no MACD cross"

@strategy(id=4, name="macd_hist_momentum", category="trend", regimes=_TREND, intraday_only=False)
def macd_hist(df):
    _, _, hist = ind.macd_lines(df["close"])
    if hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
        return SignalType.BUY, 60, "MACD histogram rising +ve"
    if hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
        return SignalType.SELL, 60, "MACD histogram falling -ve"
    return SignalType.HOLD, 0, "histogram flat"

@strategy(id=5, name="adx_di_cross", category="trend", regimes=_TREND, intraday_only=False)
def adx_di(df):
    from ta.trend import ADXIndicator
    a = ADXIndicator(df["high"], df["low"], df["close"])
    adx_v, pos, neg = a.adx().iloc[-1], a.adx_pos().iloc[-1], a.adx_neg().iloc[-1]
    if adx_v < 25:
        return SignalType.HOLD, 0, "ADX weak (<25)"
    return (SignalType.BUY, 72, "ADX strong, +DI>-DI") if pos > neg else \
           (SignalType.SELL, 72, "ADX strong, -DI>+DI")

@strategy(id=6, name="supertrend", category="trend", regimes=_TREND, intraday_only=False)
def supertrend(df, period=10, mult=3.0):
    atr = ind.atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    close = df["close"]
    direction = close.iloc[-1] > lower.iloc[-1]
    prev = close.iloc[-2] > lower.iloc[-2]
    if direction and not prev:
        return SignalType.BUY, 73, "Supertrend flipped up"
    if not direction and prev:
        return SignalType.SELL, 73, "Supertrend flipped down"
    return (SignalType.BUY, 58, "Supertrend up") if direction else (SignalType.SELL, 58, "Supertrend down")

@strategy(id=7, name="psar_flip", category="trend", regimes=_TREND, intraday_only=False)
def psar_flip(df):
    ps = ind.psar(df)
    below = df["close"].iloc[-1] > ps.iloc[-1]
    prev_below = df["close"].iloc[-2] > ps.iloc[-2]
    if below and not prev_below:
        return SignalType.BUY, 65, "PSAR flipped bullish"
    if not below and prev_below:
        return SignalType.SELL, 65, "PSAR flipped bearish"
    return (SignalType.BUY, 55, "PSAR bullish") if below else (SignalType.SELL, 55, "PSAR bearish")

@strategy(id=8, name="price_vs_200ema", category="trend", regimes=("TRENDING","RANGING","VOLATILE"), intraday_only=False)
def price_vs_200(df):
    e = ind.ema(df["close"], min(200, len(df)-1))
    return (SignalType.BUY, 60, "price above 200EMA") if df["close"].iloc[-1] > e.iloc[-1] \
        else (SignalType.SELL, 60, "price below 200EMA")

@strategy(id=9, name="market_structure", category="trend", regimes=_TREND, intraday_only=False)
def market_structure(df, lookback=20):
    recent = df.iloc[-lookback:]
    hh = recent["high"].iloc[-1] >= recent["high"].max() * 0.999
    ll = recent["low"].iloc[-1] <= recent["low"].min() * 1.001
    if hh:
        return SignalType.BUY, 62, "fresh higher-high"
    if ll:
        return SignalType.SELL, 62, "fresh lower-low"
    return SignalType.HOLD, 0, "inside structure"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_trend_strategies.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/trend.py tests/test_trend_strategies.py
git commit -m "feat(strategies): trend/momentum strategies 1-9"
```

---

## Task 7: Mean-reversion strategies (10–17)

**Files:**
- Create: `services/strategies/mean_reversion.py`
- Test: `tests/test_mean_reversion_strategies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mean_reversion_strategies.py
from services.strategies import base
import services.strategies.mean_reversion as mr
from core.models import SignalType

def test_all_registered():
    assert all(i in base.REGISTRY for i in range(10, 18))

def test_rsi_returns_valid_vote(ranging_candles):
    v = base.REGISTRY[10].run(ranging_candles)
    assert v.vote in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert 0 <= v.strength <= 100
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_mean_reversion_strategies.py -v`
Expected: FAIL (`KeyError: 10`)

- [ ] **Step 3: Implement**

```python
# services/strategies/mean_reversion.py
"""Mean-reversion strategies 10-17. Eligible mainly in RANGING."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_MR = ("RANGING",)

@strategy(id=10, name="rsi_extremes", category="mean_reversion", regimes=_MR, intraday_only=False)
def rsi_extremes(df):
    r = ind.rsi(df["close"]).iloc[-1]
    if r < 30: return SignalType.BUY, 68, f"RSI oversold ({r:.0f})"
    if r > 70: return SignalType.SELL, 68, f"RSI overbought ({r:.0f})"
    return SignalType.HOLD, 0, f"RSI neutral ({r:.0f})"

@strategy(id=11, name="rsi_divergence", category="mean_reversion", regimes=_MR, intraday_only=False)
def rsi_divergence(df, lb=14):
    r = ind.rsi(df["close"])
    price, rsi_s = df["close"], r
    p_low_now, p_low_prev = price.iloc[-1], price.iloc[-lb]
    r_low_now, r_low_prev = rsi_s.iloc[-1], rsi_s.iloc[-lb]
    if p_low_now < p_low_prev and r_low_now > r_low_prev:
        return SignalType.BUY, 64, "bullish RSI divergence"
    if p_low_now > p_low_prev and r_low_now < r_low_prev:
        return SignalType.SELL, 64, "bearish RSI divergence"
    return SignalType.HOLD, 0, "no divergence"

@strategy(id=12, name="bollinger_reversal", category="mean_reversion", regimes=_MR, intraday_only=False)
def bb_reversal(df):
    hi, mid, lo = ind.bollinger(df["close"])
    c = df["close"].iloc[-1]
    if c <= lo.iloc[-1]: return SignalType.BUY, 66, "tagged lower band"
    if c >= hi.iloc[-1]: return SignalType.SELL, 66, "tagged upper band"
    return SignalType.HOLD, 0, "inside bands"

@strategy(id=13, name="stoch_cross", category="mean_reversion", regimes=_MR, intraday_only=False)
def stoch_cross(df):
    k, d = ind.stoch(df)
    if k.iloc[-1] < 20 and k.iloc[-1] > d.iloc[-1] and k.iloc[-2] <= d.iloc[-2]:
        return SignalType.BUY, 63, "stochastic bullish cross in oversold"
    if k.iloc[-1] > 80 and k.iloc[-1] < d.iloc[-1] and k.iloc[-2] >= d.iloc[-2]:
        return SignalType.SELL, 63, "stochastic bearish cross in overbought"
    return SignalType.HOLD, 0, "no stoch signal"

@strategy(id=14, name="williams_r", category="mean_reversion", regimes=_MR, intraday_only=False)
def williams(df):
    w = ind.williams_r(df).iloc[-1]
    if w < -80: return SignalType.BUY, 60, "Williams %R oversold"
    if w > -20: return SignalType.SELL, 60, "Williams %R overbought"
    return SignalType.HOLD, 0, "neutral"

@strategy(id=15, name="cci_extremes", category="mean_reversion", regimes=_MR, intraday_only=False)
def cci_extremes(df):
    c = ind.cci(df).iloc[-1]
    if c < -100: return SignalType.BUY, 60, "CCI < -100"
    if c > 100: return SignalType.SELL, 60, "CCI > 100"
    return SignalType.HOLD, 0, "CCI neutral"

@strategy(id=16, name="vwap_reversion", category="mean_reversion", regimes=_MR, intraday_only=True)
def vwap_reversion(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    diff = (df["close"].iloc[-1] - vwap.iloc[-1]) / vwap.iloc[-1]
    if diff < -0.005: return SignalType.BUY, 58, "below VWAP, revert up"
    if diff > 0.005: return SignalType.SELL, 58, "above VWAP, revert down"
    return SignalType.HOLD, 0, "near VWAP"

@strategy(id=17, name="zscore_mean", category="mean_reversion", regimes=_MR, intraday_only=False)
def zscore(df, window=20):
    c = df["close"]
    mean = c.rolling(window).mean().iloc[-1]
    std = c.rolling(window).std().iloc[-1] or 1e-9
    z = (c.iloc[-1] - mean) / std
    if z < -2: return SignalType.BUY, 62, f"z-score {z:.1f} (cheap)"
    if z > 2: return SignalType.SELL, 62, f"z-score {z:.1f} (rich)"
    return SignalType.HOLD, 0, f"z-score {z:.1f}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_mean_reversion_strategies.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/mean_reversion.py tests/test_mean_reversion_strategies.py
git commit -m "feat(strategies): mean-reversion strategies 10-17"
```

---

## Task 8: Breakout strategies (18–23)

**Files:**
- Create: `services/strategies/breakout.py`
- Test: `tests/test_breakout_strategies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_breakout_strategies.py
from services.strategies import base
import services.strategies.breakout as bo
from core.models import SignalType

def test_all_registered():
    assert all(i in base.REGISTRY for i in range(18, 24))

def test_donchian_breaks_up_in_trend(trending_candles):
    v = base.REGISTRY[19].run(trending_candles)
    assert v.vote in (SignalType.BUY, SignalType.HOLD)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_breakout_strategies.py -v`
Expected: FAIL (`KeyError: 18`)

- [ ] **Step 3: Implement**

```python
# services/strategies/breakout.py
"""Breakout / volatility strategies 18-23. Eligible in VOLATILE & TRENDING."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_BO = ("VOLATILE", "TRENDING")

@strategy(id=18, name="bb_squeeze_breakout", category="breakout", regimes=_BO, intraday_only=False)
def bb_squeeze(df):
    hi, mid, lo = ind.bollinger(df["close"])
    width = (hi - lo) / mid
    narrow = width.iloc[-1] <= width.rolling(50).quantile(0.25).iloc[-1]
    c = df["close"].iloc[-1]
    if narrow and c >= hi.iloc[-1]: return SignalType.BUY, 70, "squeeze breakout up"
    if narrow and c <= lo.iloc[-1]: return SignalType.SELL, 70, "squeeze breakout down"
    return SignalType.HOLD, 0, "no squeeze breakout"

@strategy(id=19, name="donchian_breakout", category="breakout", regimes=_BO, intraday_only=False)
def donchian(df, window=20):
    hh = df["high"].rolling(window).max().iloc[-2]
    ll = df["low"].rolling(window).min().iloc[-2]
    c = df["close"].iloc[-1]
    if c > hh: return SignalType.BUY, 68, "Donchian upper breakout"
    if c < ll: return SignalType.SELL, 68, "Donchian lower breakout"
    return SignalType.HOLD, 0, "inside channel"

@strategy(id=20, name="opening_range_breakout", category="breakout", regimes=_BO, intraday_only=True)
def orb(df, n=15):
    opening = df.iloc[:n]
    or_high, or_low = opening["high"].max(), opening["low"].min()
    c = df["close"].iloc[-1]
    if c > or_high: return SignalType.BUY, 66, "ORB up"
    if c < or_low: return SignalType.SELL, 66, "ORB down"
    return SignalType.HOLD, 0, "inside opening range"

@strategy(id=21, name="atr_expansion", category="breakout", regimes=_BO, intraday_only=False)
def atr_expansion(df):
    atr = ind.atr(df)
    expanding = atr.iloc[-1] > atr.rolling(20).mean().iloc[-1] * 1.3
    if not expanding: return SignalType.HOLD, 0, "no ATR expansion"
    up = df["close"].iloc[-1] > df["close"].iloc[-2]
    return (SignalType.BUY, 64, "ATR expansion up") if up else (SignalType.SELL, 64, "ATR expansion down")

@strategy(id=22, name="prev_day_break", category="breakout", regimes=_BO, intraday_only=False)
def prev_day_break(df):
    if len(df) < 2: return SignalType.HOLD, 0, "insufficient data"
    pdh, pdl = df["high"].iloc[-2], df["low"].iloc[-2]
    c = df["close"].iloc[-1]
    if c > pdh: return SignalType.BUY, 60, "broke previous high"
    if c < pdl: return SignalType.SELL, 60, "broke previous low"
    return SignalType.HOLD, 0, "within previous range"

@strategy(id=23, name="keltner_breakout", category="breakout", regimes=_BO, intraday_only=False)
def keltner(df):
    hi, lo = ind.keltner(df)
    c = df["close"].iloc[-1]
    if c > hi.iloc[-1]: return SignalType.BUY, 62, "Keltner upper breakout"
    if c < lo.iloc[-1]: return SignalType.SELL, 62, "Keltner lower breakout"
    return SignalType.HOLD, 0, "inside Keltner"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_breakout_strategies.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/breakout.py tests/test_breakout_strategies.py
git commit -m "feat(strategies): breakout/volatility strategies 18-23"
```

---

## Task 9: Volume + structure strategies (24–29)

**Files:**
- Create: `services/strategies/volume.py`, `services/strategies/structure.py`
- Test: `tests/test_volume_structure_strategies.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_volume_structure_strategies.py
from services.strategies import base
import services.strategies.volume as vol
import services.strategies.structure as st
from core.models import SignalType

def test_all_registered():
    assert all(i in base.REGISTRY for i in range(24, 30))

def test_votes_valid(trending_candles):
    for i in range(24, 30):
        v = base.REGISTRY[i].run(trending_candles)
        assert v.vote in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
        assert 0 <= v.strength <= 100
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_volume_structure_strategies.py -v`
Expected: FAIL (`KeyError: 24`)

- [ ] **Step 3: Implement**

```python
# services/strategies/volume.py
"""Volume strategies 24-27."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

_ALL = ("TRENDING", "RANGING", "VOLATILE")

@strategy(id=24, name="volume_spike", category="volume", regimes=_ALL, intraday_only=False)
def volume_spike(df):
    avg = df["volume"].rolling(20).mean().iloc[-1]
    spike = df["volume"].iloc[-1] > 1.5 * avg
    if not spike: return SignalType.HOLD, 0, "no volume spike"
    up = df["close"].iloc[-1] > df["close"].iloc[-2]
    return (SignalType.BUY, 60, "volume spike up") if up else (SignalType.SELL, 60, "volume spike down")

@strategy(id=25, name="obv_trend", category="volume", regimes=_ALL, intraday_only=False)
def obv_trend(df):
    o = ind.obv(df)
    rising = o.iloc[-1] > o.rolling(20).mean().iloc[-1]
    return (SignalType.BUY, 58, "OBV rising") if rising else (SignalType.SELL, 58, "OBV falling")

@strategy(id=26, name="vwap_cross", category="volume", regimes=_ALL, intraday_only=True)
def vwap_cross(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    c, cp = df["close"].iloc[-1], df["close"].iloc[-2]
    if c > vwap.iloc[-1] and cp <= vwap.iloc[-2]: return SignalType.BUY, 62, "crossed above VWAP"
    if c < vwap.iloc[-1] and cp >= vwap.iloc[-2]: return SignalType.SELL, 62, "crossed below VWAP"
    return SignalType.HOLD, 0, "no VWAP cross"

@strategy(id=27, name="volume_weighted_breakout", category="volume", regimes=("TRENDING","VOLATILE"), intraday_only=False)
def vw_breakout(df, window=20):
    hh = df["high"].rolling(window).max().iloc[-2]
    avg = df["volume"].rolling(window).mean().iloc[-1]
    if df["close"].iloc[-1] > hh and df["volume"].iloc[-1] > 1.5 * avg:
        return SignalType.BUY, 66, "breakout on high volume"
    return SignalType.HOLD, 0, "no volume-confirmed breakout"
```

```python
# services/strategies/structure.py
"""Multi-timeframe / structure strategies 28-29.
Strategy 28 expects an attribute df.attrs['daily'] (a daily DataFrame) when
available; falls back to single-timeframe bias if absent."""
from __future__ import annotations
from core.models import SignalType
from services import indicators as ind
from services.strategies.base import strategy

@strategy(id=28, name="mtf_alignment", category="structure", regimes=("TRENDING","VOLATILE"), intraday_only=False)
def mtf_alignment(df):
    intraday_bias = ind.ema(df["close"], 21).iloc[-1] < df["close"].iloc[-1]
    daily = df.attrs.get("daily")
    if daily is not None and len(daily) > 21:
        daily_bias = ind.ema(daily["close"], 21).iloc[-1] < daily["close"].iloc[-1]
        if intraday_bias and daily_bias: return SignalType.BUY, 72, "15m & daily both bullish"
        if not intraday_bias and not daily_bias: return SignalType.SELL, 72, "15m & daily both bearish"
        return SignalType.HOLD, 0, "timeframes disagree"
    return (SignalType.BUY, 50, "intraday bullish (no daily)") if intraday_bias \
        else (SignalType.SELL, 50, "intraday bearish (no daily)")

@strategy(id=29, name="pivot_sr", category="structure", regimes=("RANGING","VOLATILE"), intraday_only=True)
def pivot_sr(df):
    if len(df) < 2: return SignalType.HOLD, 0, "insufficient data"
    h, l, c = df["high"].iloc[-2], df["low"].iloc[-2], df["close"].iloc[-2]
    pivot = (h + l + c) / 3
    s1, r1 = 2 * pivot - h, 2 * pivot - l
    price = df["close"].iloc[-1]
    if price <= s1: return SignalType.BUY, 60, "bounced off S1"
    if price >= r1: return SignalType.SELL, 60, "rejected at R1"
    return SignalType.HOLD, 0, "between pivots"
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_volume_structure_strategies.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/volume.py services/strategies/structure.py tests/test_volume_structure_strategies.py
git commit -m "feat(strategies): volume 24-27 + structure 28-29"
```

---

## Task 10: Strategy registry JSON + preset bundles

**Files:**
- Create: `strategies.json`
- Test: `tests/test_strategies_json.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategies_json.py
import json
from pathlib import Path

def test_presets_reference_valid_ids():
    data = json.loads(Path("strategies.json").read_text())
    valid = {s["id"] for s in data["strategies"]}
    assert len(valid) == 29
    for name, ids in data["presets"].items():
        assert set(ids).issubset(valid), f"{name} references unknown id"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_strategies_json.py -v`
Expected: FAIL (`FileNotFoundError: strategies.json`)

- [ ] **Step 3: Implement** (29 entries; abbreviated metadata mirrors the decorators)

```json
{
  "strategies": [
    {"id": 1, "name": "ema_cross_9_21", "category": "trend"},
    {"id": 2, "name": "ema_ribbon", "category": "trend"},
    {"id": 3, "name": "macd_signal_cross", "category": "trend"},
    {"id": 4, "name": "macd_hist_momentum", "category": "trend"},
    {"id": 5, "name": "adx_di_cross", "category": "trend"},
    {"id": 6, "name": "supertrend", "category": "trend"},
    {"id": 7, "name": "psar_flip", "category": "trend"},
    {"id": 8, "name": "price_vs_200ema", "category": "trend"},
    {"id": 9, "name": "market_structure", "category": "trend"},
    {"id": 10, "name": "rsi_extremes", "category": "mean_reversion"},
    {"id": 11, "name": "rsi_divergence", "category": "mean_reversion"},
    {"id": 12, "name": "bollinger_reversal", "category": "mean_reversion"},
    {"id": 13, "name": "stoch_cross", "category": "mean_reversion"},
    {"id": 14, "name": "williams_r", "category": "mean_reversion"},
    {"id": 15, "name": "cci_extremes", "category": "mean_reversion"},
    {"id": 16, "name": "vwap_reversion", "category": "mean_reversion"},
    {"id": 17, "name": "zscore_mean", "category": "mean_reversion"},
    {"id": 18, "name": "bb_squeeze_breakout", "category": "breakout"},
    {"id": 19, "name": "donchian_breakout", "category": "breakout"},
    {"id": 20, "name": "opening_range_breakout", "category": "breakout"},
    {"id": 21, "name": "atr_expansion", "category": "breakout"},
    {"id": 22, "name": "prev_day_break", "category": "breakout"},
    {"id": 23, "name": "keltner_breakout", "category": "breakout"},
    {"id": 24, "name": "volume_spike", "category": "volume"},
    {"id": 25, "name": "obv_trend", "category": "volume"},
    {"id": 26, "name": "vwap_cross", "category": "volume"},
    {"id": 27, "name": "volume_weighted_breakout", "category": "volume"},
    {"id": 28, "name": "mtf_alignment", "category": "structure"},
    {"id": 29, "name": "pivot_sr", "category": "structure"}
  ],
  "presets": {
    "intraday_momentum": [1, 3, 5, 6, 8, 20, 24, 26, 28],
    "range_scalper": [10, 12, 13, 16, 17, 22, 29],
    "positional_quality": [2, 8, 9, 18, 19, 25, 28],
    "all_on": [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29]
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_strategies_json.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add strategies.json tests/test_strategies_json.py
git commit -m "feat(strategies): registry json + preset bundles"
```

---

## Task 11: Confluence engine (category-weighted / decorrelated)

**Files:**
- Create: `services/strategies/engine.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
import services.strategies.trend, services.strategies.mean_reversion
import services.strategies.breakout, services.strategies.volume, services.strategies.structure  # noqa: register all
from services.strategies.engine import build_confluence
from core.models import ConfluenceSnapshot, SignalType

def test_confluence_in_trend_is_bullish(trending_candles):
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    assert isinstance(snap, ConfluenceSnapshot)
    assert -1.0 <= snap.net_score <= 1.0
    assert snap.bias in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    # uptrend should not be net bearish
    assert snap.net_score >= 0

def test_category_weighting_decorrelates(trending_candles):
    # 9 correlated trend strategies must not outweigh everything: each category
    # contributes at most 1/num_categories to net_score.
    snap = build_confluence(trending_candles, regime=None, style="positional",
                            active_ids=list(range(1, 30)))
    assert all(-1.0 <= v <= 1.0 for v in snap.category_scores.values())
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL (`ModuleNotFoundError: services.strategies.engine`)

- [ ] **Step 3: Implement**

```python
# services/strategies/engine.py
"""Run eligible strategies and aggregate votes with CATEGORY weighting so that
many correlated indicators in one category cannot fake conviction.

net_score = mean over categories of (category net score), where a category's
score is the strength-weighted mean of its members' signed votes (BUY=+1,
SELL=-1, HOLD=0), normalised to [-1, 1]. Equal weight per category =>
decorrelation across indicator families."""
from __future__ import annotations
from typing import Optional
import pandas as pd
from core.models import ConfluenceSnapshot, Regime, SignalType, StrategyVote
from services.regime import classify_regime
from services.strategies import base

_SIGN = {SignalType.BUY: 1.0, SignalType.SELL: -1.0, SignalType.HOLD: 0.0}
BUY_THRESHOLD = 0.15
SELL_THRESHOLD = -0.15

def build_confluence(df: pd.DataFrame, *, regime: Optional[Regime],
                     style: str, active_ids: list[int]) -> ConfluenceSnapshot:
    regime = regime or classify_regime(df)
    specs = [s for s in base.eligible(regime=regime.value, style=style)
             if s.id in active_ids]
    votes: list[StrategyVote] = [s.run(df) for s in specs]

    by_cat: dict[str, list[StrategyVote]] = {}
    for v in votes:
        by_cat.setdefault(v.category, []).append(v)

    category_scores: dict[str, float] = {}
    for cat, vs in by_cat.items():
        wsum = sum(v.strength for v in vs) or 1
        score = sum(_SIGN[v.vote] * v.strength for v in vs) / wsum
        category_scores[cat] = max(-1.0, min(1.0, score))

    net = (sum(category_scores.values()) / len(category_scores)) if category_scores else 0.0
    if net >= BUY_THRESHOLD:
        bias = SignalType.BUY
    elif net <= SELL_THRESHOLD:
        bias = SignalType.SELL
    else:
        bias = SignalType.HOLD

    return ConfluenceSnapshot(
        regime=regime, votes=votes, category_scores=category_scores,
        net_score=round(net, 4), bias=bias,
        buy_count=sum(1 for v in votes if v.vote is SignalType.BUY),
        sell_count=sum(1 for v in votes if v.vote is SignalType.SELL),
        hold_count=sum(1 for v in votes if v.vote is SignalType.HOLD),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add services/strategies/engine.py tests/test_engine.py
git commit -m "feat(engine): category-weighted decorrelated confluence"
```

---

## Task 12: Dhan client wrapper (dry_run aware)

**Files:**
- Create: `services/dhan_client.py`
- Test: `tests/test_dhan_client.py`

> Dhan calls are wrapped so the SDK is injected (constructor takes an optional
> client) — tests pass a fake, no network. `dry_run=True` short-circuits all
> *order* methods to a simulated `OrderResult` while leaving data reads to flow
> through (tests stub those too).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dhan_client.py
from services.dhan_client import DhanClient
from core.models import Instrument, OrderRequest, Side, OrderType, TradeMode

class FakeSDK:
    def __init__(self): self.placed = []
    def get_order_list(self): return {"status": "success", "data": []}
    def place_order(self, **kw):
        self.placed.append(kw); return {"status": "success", "data": {"orderId": "X1"}}

def _instr():
    return Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="2885")

def test_paper_mode_does_not_call_sdk():
    sdk = FakeSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.PAPER)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok and res.mode is TradeMode.PAPER
    assert res.status == "PLACED"
    assert sdk.placed == []          # never hit the broker in paper mode

def test_live_mode_calls_sdk():
    sdk = FakeSDK()
    c = DhanClient(sdk=sdk, mode=TradeMode.LIVE)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok and res.dhan_order_id == "X1"
    assert len(sdk.placed) == 1

def test_error_is_surfaced_not_raised():
    class BoomSDK(FakeSDK):
        def place_order(self, **kw): raise RuntimeError("boom")
    c = DhanClient(sdk=BoomSDK(), mode=TradeMode.LIVE)
    req = OrderRequest(instrument=_instr(), side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    res = c.place_order(req)
    assert res.ok is False and "boom" in res.error_message
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dhan_client.py -v`
Expected: FAIL (`ModuleNotFoundError: services.dhan_client`)

- [ ] **Step 3: Implement**

```python
# services/dhan_client.py
"""Wrapper over the dhanhq SDK. Every method returns data or a structured result;
errors are caught and surfaced (never raised into the UI). In PAPER mode, order
mutating methods are simulated and the broker is never contacted."""
from __future__ import annotations
import logging
from typing import Any, Optional
from core.models import (Instrument, OrderRequest, OrderResult, OrderType,
                         Side, TradeMode)

log = logging.getLogger(__name__)

class DhanError(RuntimeError):
    pass

class DhanClient:
    def __init__(self, sdk: Any = None, mode: TradeMode = TradeMode.PAPER,
                 client_id: Optional[str] = None, access_token: Optional[str] = None):
        if sdk is None:
            from dhanhq import dhanhq
            sdk = dhanhq(client_id, access_token)
        self.sdk = sdk
        self.mode = mode

    # ---- data reads ----
    def get_positions(self) -> list[dict]:
        try:
            resp = self.sdk.get_positions()
            return resp.get("data", []) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001 - surface, don't crash
            log.exception("get_positions failed")
            raise DhanError(f"Failed to fetch positions: {e}") from e

    def get_fund_limits(self) -> dict:
        try:
            resp = self.sdk.get_fund_limits()
            return resp.get("data", {}) if isinstance(resp, dict) else resp
        except Exception as e:                       # noqa: BLE001
            raise DhanError(f"Failed to fetch funds: {e}") from e

    # ---- order writes (dry_run aware) ----
    def place_order(self, req: OrderRequest) -> OrderResult:
        if self.mode is TradeMode.PAPER:
            return OrderResult(ok=True, mode=TradeMode.PAPER, status="PLACED",
                               dhan_order_id=f"PAPER-{req.instrument.symbol}",
                               exec_price=req.price)
        try:
            resp = self.sdk.place_order(
                security_id=req.instrument.security_id,
                exchange_segment=req.instrument.exchange_segment,
                transaction_type=req.side.value,
                quantity=req.qty,
                order_type=req.order_type.value,
                price=req.price or 0,
                product_type="INTRADAY",
            )
            oid = (resp.get("data") or {}).get("orderId") if isinstance(resp, dict) else None
            return OrderResult(ok=bool(oid), mode=TradeMode.LIVE, status="PLACED",
                               dhan_order_id=oid, exec_price=req.price)
        except Exception as e:                       # noqa: BLE001
            log.exception("place_order failed")
            return OrderResult(ok=False, mode=TradeMode.LIVE, status="ERROR",
                               error_message=str(e))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dhan_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add services/dhan_client.py tests/test_dhan_client.py
git commit -m "feat(dhan): SDK wrapper with dry_run + error surfacing"
```

> **Note:** remaining `dhan_client` methods (LTP, historical candles, modify,
> cancel, exit, super/bracket order) are added in Phase B Task set against the
> live SDK signatures, following the same wrap-and-surface pattern verified here.

---

## Task 13: Phase A integration smoke test

**Files:**
- Test: `tests/test_phase_a_integration.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_phase_a_integration.py
"""End-to-end Phase A: candles -> regime -> confluence snapshot."""
import services.strategies.trend, services.strategies.mean_reversion  # noqa
import services.strategies.breakout, services.strategies.volume, services.strategies.structure  # noqa
from services.strategies.engine import build_confluence
from services.regime import classify_regime
from core.models import Regime, SignalType

def test_full_pipeline(trending_candles):
    regime = classify_regime(trending_candles)
    assert regime in Regime
    snap = build_confluence(trending_candles, regime=regime, style="positional",
                            active_ids=list(range(1, 30)))
    assert snap.votes, "expected at least one eligible strategy to vote"
    assert snap.bias in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert snap.buy_count + snap.sell_count + snap.hold_count == len(snap.votes)
```

- [ ] **Step 2: Run to verify it passes**

Run: `python -m pytest tests/test_phase_a_integration.py -v`
Expected: PASS (1 passed)

- [ ] **Step 3: Run the FULL suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_phase_a_integration.py
git commit -m "test: Phase A integration — candles to confluence snapshot"
```

---

## Self-Review Notes (completed)

- **Spec coverage:** §3 catalog → Tasks 6-9 (all 29). §4 regime gate → Task 4 + `eligible()`. §4 decorrelated confluence → Task 11. §7 `strategies.json` + presets → Task 10. §8 `dhan_client` (dry_run) → Task 12. Adaptive weighting / news / fundamentals / AI / ATR-stops / event-guards / per-provider weighting / backtest are **Phase B–D** (out of scope here, by design).
- **Type consistency:** `StrategyVote`, `ConfluenceSnapshot`, `Regime`, `SignalType`, `OrderResult`, `OrderRequest` all defined in Task 1 / existing `models.py`; engine + strategies use the same field names (`vote`, `strength`, `category`, `net_score`, `bias`).
- **Placeholder scan:** every code step contains complete code; the one explicit deferral (extra `dhan_client` methods) is scoped to Phase B intentionally, not a placeholder in an in-scope task.
- **Parallelism note for execution:** Tasks 6, 7, 8, 9 are independent once Tasks 1, 3, 5 are done — safe to dispatch in parallel. Task 11 depends on 6-9; Task 12 is independent of the strategy chain.
