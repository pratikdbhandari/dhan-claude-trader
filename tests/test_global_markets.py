"""global_markets: driver mapping, cue math, risk sentiment, FII/DII parsing,
event classification — all offline with injected data."""
from __future__ import annotations

from services import analysis, global_markets as gm


def _rows(**pcts):
    return {t: {"name": gm._BY_TICKER.get(t, t), "ticker": t, "group": "x",
                "last": 100.0, "pct": p} for t, p in pcts.items()}


def _reset():
    gm._cache.update(ts=0.0, rows={})
    gm._flows_cache.update(ts=0.0, flows=[])


def test_every_universe_symbol_has_a_sector():
    from services.market_feed import load_universe
    for i in load_universe("universe.json"):
        assert i.symbol in gm.SECTOR, f"{i.symbol} missing from SECTOR map"


def test_every_sector_has_drivers():
    for sector in set(gm.SECTOR.values()):
        assert sector in gm.DRIVERS, f"{sector} missing from DRIVERS map"


def test_it_stock_supported_by_nasdaq_and_weak_rupee():
    rows = _rows(**{"^IXIC": 1.5, "^GSPC": 0.5, "INR=X": 0.4})
    out = gm.stock_drivers("TCS", rows)
    assert out["sector"] == "IT"
    assert out["cue"] == "SUPPORTIVE" and out["score"] > 0
    nasdaq = next(d for d in out["drivers"] if d["ticker"] == "^IXIC")
    assert nasdaq["aligned"] == 1.5


def test_refiner_hurt_by_rising_crude():
    rows = _rows(**{"BZ=F": 2.0})
    out = gm.stock_drivers("BPCL", rows)
    assert out["cue"] == "AGAINST" and out["score"] == -2.0
    up = gm.stock_drivers("ONGC", rows)
    assert up["cue"] == "SUPPORTIVE" and up["score"] == 2.0


def test_unknown_symbol_falls_back_to_index_drivers():
    out = gm.stock_drivers("WHOKNOWS", _rows(**{"^GSPC": 1.0}))
    assert out["sector"] == "INDEX"


def test_risk_sentiment_labels():
    on = gm.risk_sentiment(_rows(**{"^GSPC": 1.0, "^IXIC": 1.2, "^N225": 0.8,
                                    "^HSI": 0.5, "^FTSE": 0.3}))
    assert on["label"] == "RISK-ON"
    off = gm.risk_sentiment(_rows(**{"^GSPC": -1.0, "^IXIC": -1.2, "^N225": -0.8,
                                     "^HSI": -0.5, "^FTSE": -0.3}))
    assert off["label"] == "RISK-OFF"
    assert gm.risk_sentiment({})["label"] == "UNKNOWN"


def test_snapshot_caches_and_degrades():
    _reset()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return _rows(**{"^GSPC": 1.0})

    r1 = gm.snapshot(ttl=600, fetch=fetch)
    r2 = gm.snapshot(ttl=600, fetch=fetch)
    assert r1 == r2 and calls["n"] == 1

    def boom():
        raise RuntimeError("down")
    _reset()
    assert gm.snapshot(ttl=600, fetch=boom) == {}


def test_fii_dii_parses_nse_shape():
    _reset()
    def fetch():
        return [{"category": "DII", "date": "15-Jul-2026", "buy": 1, "sell": 2,
                 "net": -1}]
    # fetch already normalised — fii_dii passes it through the cache layer
    flows = gm.fii_dii(fetch=fetch)
    assert flows[0]["category"] == "DII"


def test_corporate_event_classification():
    heads = ["Reliance bags mega contract from defence ministry",
             "Reliance promoter entities pledge additional shares",
             "Reliance Q1 results: profit rises 12%",
             "New CFO appointed at Reliance Industries",
             "FII stake in Reliance rises in June quarter",
             "Nifty ends flat"]
    events = analysis.classify_corporate_events("RELIANCE", heads)
    cats = {c for e in events for c in e["categories"]}
    assert {"ORDERS", "PLEDGE", "RESULTS", "MANAGEMENT", "HOLDING CHANGE"} <= cats
    assert all("Nifty" not in e["title"] for e in events)


def test_global_cues_flow_into_pros_and_cons():
    import numpy as np
    import pandas as pd
    from core.models import Instrument
    rng = np.random.default_rng(7)
    close = 100 + np.linspace(0, 40, 250) + rng.normal(0, 0.4, 250)
    df = pd.DataFrame({"open": close - 0.2, "high": close + 1.2,
                       "low": close - 1.2, "close": close,
                       "volume": rng.uniform(1000, 5000, 250)})
    instr = Instrument(symbol="TCS", exchange_segment="NSE_EQ", security_id="1")
    cues = gm.stock_drivers("TCS", _rows(**{"^IXIC": 1.5, "^GSPC": 0.5,
                                            "INR=X": 0.4}))
    a = analysis.analyze_frame(instr, df, style="positional", headlines=[],
                               fundamentals={}, event_flags=[], global_cues=cues)
    assert a["signal"] == "BUY"
    assert any("Global cues support" in p for p in a["pros"])
    against = gm.stock_drivers("TCS", _rows(**{"^IXIC": -2.0, "^GSPC": -1.0,
                                               "INR=X": -0.5}))
    a2 = analysis.analyze_frame(instr, df, style="positional", headlines=[],
                                fundamentals={}, event_flags=[], global_cues=against)
    assert any("Global cues work against" in c for c in a2["cons"])
