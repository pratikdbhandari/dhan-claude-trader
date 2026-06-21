from services.instruments import build_index, resolve, resolve_watchlist
from core.models import Instrument

SAMPLE_CSV = """SEM_TRADING_SYMBOL,SEM_EXM_EXCH_ID,SEM_SMST_SECURITY_ID
RELIANCE,NSE,2885
NIFTY,IDX,13
HDFCBANK,NSE,1333
"""


def test_build_index_maps_symbol_segment_to_id():
    idx = build_index(SAMPLE_CSV)
    assert idx[("RELIANCE", "NSE")] == "2885"
    assert idx[("NIFTY", "IDX")] == "13"


def test_resolve_fills_security_id():
    idx = build_index(SAMPLE_CSV)
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                       security_id=None, kind="EQUITY")
    out = resolve(instr, idx)
    assert out.security_id == "2885"


def test_resolve_index_instrument():
    idx = build_index(SAMPLE_CSV)
    instr = Instrument(symbol="NIFTY", exchange_segment="IDX_I", security_id=None,
                       kind="INDEX")
    assert resolve(instr, idx).security_id == "13"


def test_resolve_unknown_stays_none():
    idx = build_index(SAMPLE_CSV)
    instr = Instrument(symbol="UNKNOWNX", exchange_segment="NSE_EQ", security_id=None)
    assert resolve(instr, idx).security_id is None


def test_resolve_preserves_existing_id():
    idx = build_index(SAMPLE_CSV)
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="999")
    assert resolve(instr, idx).security_id == "999"


def test_build_index_garbage_returns_empty():
    assert build_index("not,a,valid\nmaster") == {}


def test_resolve_watchlist_batch():
    idx = build_index(SAMPLE_CSV)
    wl = [Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ"),
          Instrument(symbol="HDFCBANK", exchange_segment="NSE_EQ")]
    out = resolve_watchlist(wl, idx)
    assert [i.security_id for i in out] == ["2885", "1333"]
