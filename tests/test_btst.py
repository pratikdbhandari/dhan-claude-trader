import numpy as np
import pandas as pd

from core.models import (ConfluenceSnapshot, Instrument, Regime, SignalType)
from services.btst import scan


def _instr(sym="RELIANCE"):
    return Instrument(symbol=sym, exchange_segment="NSE_EQ", security_id="1")


def _daily(n=40, *, last_close=None, last_high=None, last_low=None,
           last_open=None, vol_last=None, vol_base=1000.0):
    rng = np.random.default_rng(0)
    close = np.linspace(90, 100, n)
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.2
    vol = np.full(n, vol_base)
    if last_close is not None: close[-1] = last_close
    if last_high is not None: high[-1] = last_high
    if last_low is not None: low[-1] = last_low
    if last_open is not None: open_[-1] = last_open
    if vol_last is not None: vol[-1] = vol_last
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def _bull_snap(net=0.4):
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[], category_scores={},
                              net_score=net, bias=SignalType.BUY,
                              buy_count=5, sell_count=0, hold_count=0)


def _bear_snap():
    return ConfluenceSnapshot(regime=Regime.TRENDING, votes=[], category_scores={},
                              net_score=-0.4, bias=SignalType.SELL,
                              buy_count=0, sell_count=5, hold_count=0)


def _passing_df():
    return _daily(last_open=99.0, last_close=103.4, last_high=104.0, last_low=98.0,
                  vol_last=2000.0, vol_base=1000.0)


def test_passing_candidate_appears_with_plan():
    out = scan([_instr()], candles_fn=lambda i: _passing_df(),
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert len(out) == 1
    c = out[0]
    assert c.instrument.symbol == "RELIANCE"
    assert c.entry == 103.4
    assert c.target > c.entry > c.stop
    assert c.close_strength >= 0.7
    assert c.volume_ratio >= 1.2
    assert c.gap_risk
    assert any("close" in r.lower() for r in c.reasons)


def test_bearish_bias_rejected():
    out = scan([_instr()], candles_fn=lambda i: _passing_df(),
               confluence_fn=lambda df: _bear_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_weak_close_rejected():
    df = _daily(last_open=99.0, last_close=98.6, last_high=104.0, last_low=98.0,
                vol_last=2000.0, vol_base=1000.0)
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_low_volume_rejected():
    df = _daily(last_open=99.0, last_close=103.4, last_high=104.0, last_low=98.0,
                vol_last=1000.0, vol_base=1000.0)
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_red_candle_rejected():
    df = _daily(last_open=104.0, last_close=103.4, last_high=104.5, last_low=98.0,
                vol_last=2000.0, vol_base=1000.0)
    out = scan([_instr()], candles_fn=lambda i: df,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_insufficient_candles_skipped():
    out = scan([_instr()], candles_fn=lambda i: _daily(n=5),
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)),
               avg_vol_lookback=20)
    assert out == []


def test_fetch_error_skipped_not_fatal():
    def boom(i):
        raise RuntimeError("no data")
    out = scan([_instr()], candles_fn=boom,
               confluence_fn=lambda df: _bull_snap(), active_ids=list(range(1, 30)))
    assert out == []


def test_ranking_by_score_times_strength():
    a, b = _instr("AAA"), _instr("BBB")
    def cf(df):
        return _bull_snap(net=0.4)
    def candles(i):
        if i.symbol == "BBB":
            return _daily(last_open=99.0, last_close=103.9, last_high=104.0,
                          last_low=98.0, vol_last=2000.0)
        return _passing_df()
    out = scan([a, b], candles_fn=candles, confluence_fn=cf,
               active_ids=list(range(1, 30)))
    assert [c.instrument.symbol for c in out] == ["BBB", "AAA"]
