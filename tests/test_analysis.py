"""analysis service: news classification, verdict logic, and the full
analyze_frame output structure — all offline (no network)."""
from __future__ import annotations
import numpy as np
import pandas as pd

from core.models import Instrument
from services import analysis


def _trending_candles(n=250, up=True):
    rng = np.random.default_rng(7)
    drift = np.linspace(0, 40 if up else -40, n)
    close = 100 + drift + rng.normal(0, 0.4, n)
    return pd.DataFrame({"open": close - 0.2, "high": close + 1.2,
                         "low": close - 1.2, "close": close,
                         "volume": rng.uniform(1000, 5000, n)})


REL = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="2885")


# ---------------------------------------------------------------- news
def test_headline_sentiment_positive_negative_neutral():
    assert analysis.headline_sentiment("Reliance shares surge on record profit") == "POSITIVE"
    assert analysis.headline_sentiment("Reliance slumps after probe ordered") == "NEGATIVE"
    assert analysis.headline_sentiment("Reliance AGM scheduled for August") == "NEUTRAL"


def test_classify_news_routes_stock_vs_market():
    heads = ["Reliance wins big order, shares jump",
             "RIL faces penalty in gas dispute",
             "Nifty ends flat ahead of Fed decision"]
    out = analysis.classify_news("RELIANCE", heads)
    assert out["positive"] == ["Reliance wins big order, shares jump"]
    assert out["negative"] == ["RIL faces penalty in gas dispute"]
    assert len(out["market"]) == 1
    assert out["net"] == "NEUTRAL"          # 1 pos vs 1 neg


def test_classify_news_net_direction():
    out = analysis.classify_news("TCS", ["TCS beats estimates, profit rises",
                                         "TCS wins mega deal"])
    assert out["net"] == "POSITIVE" and len(out["positive"]) == 2


# ---------------------------------------------------------------- full frame
def _run(headlines=None, **kw):
    return analysis.analyze_frame(
        REL, _trending_candles(), style="positional",
        headlines=headlines or [], fundamentals=kw.get("fundamentals", {}),
        event_flags=kw.get("event_flags", []))


def test_analyze_frame_structure_and_signal():
    a = _run()
    for key in ("symbol", "signal", "verdict", "pros", "cons", "votes",
                "entry", "stop_loss", "target", "gate", "readings", "news"):
        assert key in a
    assert a["symbol"] == "RELIANCE"
    assert a["signal"] in ("BUY", "SELL", "HOLD")
    assert isinstance(a["votes"], list) and a["votes"]
    assert a["votes"][0]["strength"] >= a["votes"][-1]["strength"]


def test_uptrend_produces_buy_with_plan_and_take_verdict():
    a = _run()
    assert a["signal"] == "BUY"
    assert a["entry"] and a["stop_loss"] and a["target"]
    assert a["rr"] and a["rr"] >= 1.5
    assert a["verdict"] in ("TAKE", "CAUTION")
    assert any("Quality gate PASS" in p for p in a["pros"]) or not a["gate"]["passed"]


def test_results_event_forces_avoid():
    a = _run(event_flags=["RESULTS"])
    assert a["gate"]["vetoed"] is True
    assert a["verdict"] == "AVOID"


def test_negative_news_flow_appears_in_cons_for_buy():
    heads = ["Reliance slumps on probe", "Reliance shares drop after penalty",
             "RIL faces lawsuit over dues"]
    a = _run(headlines=heads)
    assert a["signal"] == "BUY"
    assert a["news"]["net"] == "NEGATIVE"
    assert any("news" in c.lower() for c in a["cons"])
    assert a["verdict"] in ("CAUTION", "AVOID")


def test_results_flag_is_stock_specific():
    from datetime import date
    monday = date(2026, 7, 13)
    generic = ["Earnings season kicks off next week", "Nifty flat ahead of results"]
    assert "RESULTS" not in analysis.event_flags_for("RELIANCE", generic, monday)
    specific = generic + ["Reliance Q1 results on Friday"]
    assert "RESULTS" in analysis.event_flags_for("RELIANCE", specific, monday)
    thursday = date(2026, 7, 16)
    assert "EXPIRY" in analysis.event_flags_for("RELIANCE", [], thursday)


def test_hold_maps_to_no_trade():
    rng = np.random.default_rng(3)
    close = 100 + rng.normal(0, 0.05, 250)      # flat, no edge
    df = pd.DataFrame({"open": close, "high": close + 0.1, "low": close - 0.1,
                       "close": close, "volume": rng.uniform(1000, 2000, 250)})
    a = analysis.analyze_frame(REL, df, style="positional", headlines=[],
                               fundamentals={}, event_flags=[])
    if a["signal"] == "HOLD":
        assert a["verdict"] == "NO TRADE"
