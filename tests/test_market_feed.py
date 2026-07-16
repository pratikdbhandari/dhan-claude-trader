"""market_feed: batched snapshot parsing, TTL/throttle caching, movers ranking,
universe loading. A fake SDK stands in for dhanhq — no network."""
from __future__ import annotations
import json

import pytest

from core.models import Instrument
from services import market_feed


def _reset_cache():
    market_feed._cache.update(key=None, ts=0.0, rows={}, ok_wall=0.0)
    market_feed._last_call_ts = 0.0


NIFTY = Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id="13",
                   kind="INDEX")
REL = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="2885")
TCS = Instrument(symbol="TCS", exchange_segment="NSE_EQ", security_id="11536")


def _resp(rows_by_seg):
    return {"status": "success", "remarks": "",
            "data": {"data": rows_by_seg, "status": "success"}}


class FakeSDK:
    def __init__(self, resp):
        self.resp = resp
        self.calls = 0

    def ohlc_data(self, securities):
        self.calls += 1
        self.last_securities = securities
        return self.resp


SAMPLE = _resp({
    "IDX_I": {"13": {"last_price": 24140.3,
                     "ohlc": {"open": 24142.1, "close": 24078.5,
                              "high": 24167.4, "low": 24097.05}}},
    "NSE_EQ": {"2885": {"last_price": 1306.0,
                        "ohlc": {"open": 1295.5, "close": 1295.5,
                                 "high": 1309.4, "low": 1295.5}},
               "11536": {"last_price": 3050.0,
                         "ohlc": {"open": 3105.0, "close": 3100.0,
                                  "high": 3110.0, "low": 3045.0}}}})


def test_securities_map_groups_by_segment_and_skips_unresolved():
    unresolved = Instrument(symbol="X", exchange_segment="NSE_EQ", security_id=None)
    m = market_feed.securities_map([NIFTY, REL, TCS, unresolved])
    assert m == {"IDX_I": [13], "NSE_EQ": [2885, 11536]}


def test_snapshot_parses_and_quotes_join():
    _reset_cache()
    sdk = FakeSDK(SAMPLE)
    rows = market_feed.fetch_snapshot(sdk, [NIFTY, REL, TCS])
    quotes = market_feed.quotes_for(rows, [NIFTY, REL, TCS])
    assert [q.symbol for q in quotes] == ["NIFTY", "RELIANCE", "TCS"]
    nifty = quotes[0]
    assert nifty.ltp == 24140.3 and nifty.prev_close == 24078.5
    assert nifty.change == pytest.approx(61.8, abs=0.01)
    assert nifty.pct == pytest.approx(0.26, abs=0.01)


def test_snapshot_caches_within_ttl_one_broker_call():
    _reset_cache()
    sdk = FakeSDK(SAMPLE)
    market_feed.fetch_snapshot(sdk, [NIFTY, REL], ttl=3.0, now=100.0)
    market_feed.fetch_snapshot(sdk, [NIFTY, REL], ttl=3.0, now=101.0)
    market_feed.fetch_snapshot(sdk, [NIFTY, REL], ttl=3.0, now=102.9)
    assert sdk.calls == 1
    market_feed.fetch_snapshot(sdk, [NIFTY, REL], ttl=3.0, now=103.5)
    assert sdk.calls == 2


def test_snapshot_serves_stale_on_failure():
    _reset_cache()
    sdk = FakeSDK(SAMPLE)
    rows1 = market_feed.fetch_snapshot(sdk, [NIFTY], ttl=1.0, now=10.0)
    sdk.resp = {"status": "failure", "remarks": "805", "data": ""}
    rows2 = market_feed.fetch_snapshot(sdk, [NIFTY], ttl=1.0, now=20.0)
    assert rows2 == rows1 and rows1  # stale snapshot, not empty


def test_snapshot_never_raises_on_sdk_exception():
    _reset_cache()

    class Boom:
        def ohlc_data(self, s):
            raise RuntimeError("network down")

    assert market_feed.fetch_snapshot(Boom(), [NIFTY], now=5.0) == {}


def test_movers_ranks_by_pct_and_excludes_indices():
    def q(sym, ltp, prev, kind="EQUITY"):
        return market_feed.Quote(symbol=sym, security_id="1",
                                 exchange_segment="NSE_EQ", kind=kind, ltp=ltp,
                                 prev_close=prev, open=0, high=0, low=0)
    quotes = [q("UP2", 110, 100), q("UP1", 105, 100), q("DOWN", 90, 100),
              q("FLAT", 100, 100), q("NIFTY", 25000, 24000, kind="INDEX")]
    gainers, losers = market_feed.movers(quotes, n=2)
    assert [g.symbol for g in gainers] == ["UP2", "UP1"]
    assert [l.symbol for l in losers] == ["DOWN"]


# ---------------------------------------------------------------- staleness
def test_staleness_before_any_success_is_stale():
    _reset_cache()
    s = market_feed.staleness()
    assert s["stale"] is True and s["age"] is None and s["last"] is None


def test_staleness_fresh_after_successful_fetch():
    _reset_cache()
    market_feed.fetch_snapshot(FakeSDK(SAMPLE), [NIFTY], now=1.0)
    s = market_feed.staleness()
    assert s["stale"] is False and s["age"] == 0 and s["last"]


def test_staleness_goes_stale_after_threshold():
    _reset_cache()
    market_feed.fetch_snapshot(FakeSDK(SAMPLE), [NIFTY], now=1.0)
    ok = market_feed._cache["ok_wall"]
    assert market_feed.staleness(now=ok + market_feed.STALE_AFTER - 1)["stale"] is False
    late = market_feed.staleness(now=ok + market_feed.STALE_AFTER + 1)
    assert late["stale"] is True and late["age"] == int(market_feed.STALE_AFTER + 1)


def test_dead_token_midsession_serves_stale_but_flags_it():
    """The 09:21 bug: caches warm, then the broker dies. Prices may stay on
    screen, but staleness() must stop calling them live."""
    _reset_cache()
    sdk = FakeSDK(SAMPLE)
    rows = market_feed.fetch_snapshot(sdk, [NIFTY], ttl=1.0, now=10.0)
    ok_before = market_feed._cache["ok_wall"]
    assert market_feed.staleness()["stale"] is False

    sdk.resp = {"status": "failure", "remarks": "Invalid token", "data": ""}
    still = market_feed.fetch_snapshot(sdk, [NIFTY], ttl=1.0, now=20.0)
    assert still == rows                              # stale frame still served
    assert market_feed._cache["ok_wall"] == ok_before  # success time NOT bumped
    assert market_feed.staleness(now=ok_before + 31)["stale"] is True


def test_load_universe_reads_json(tmp_path):
    p = tmp_path / "u.json"
    p.write_text(json.dumps({"instruments": [
        {"symbol": "TCS", "exchange_segment": "NSE_EQ", "security_id": "11536"}]}))
    uni = market_feed.load_universe(p)
    assert uni == [Instrument(symbol="TCS", exchange_segment="NSE_EQ",
                              security_id="11536")]


def test_load_universe_missing_file_degrades_to_empty(tmp_path):
    assert market_feed.load_universe(tmp_path / "nope.json") == []


def test_project_universe_file_is_valid():
    uni = market_feed.load_universe("universe.json")
    assert len(uni) >= 40
    assert all(i.security_id for i in uni)
    assert all(i.exchange_segment == "NSE_EQ" for i in uni)
