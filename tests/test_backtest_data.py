import pandas as pd
from services.backtest_data import load_candles
from core.models import Instrument


def _instr():
    return Instrument(symbol="X", exchange_segment="NSE_EQ", security_id="1",
                      kind="EQUITY")


class FakeDhan:
    def __init__(self):
        self.calls = 0

    def get_candles(self, instrument, interval, lookback_days):
        self.calls += 1
        return pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0],
                             "close": [1.0], "volume": [1.0]})


def test_fetch_and_cache_then_reuse(tmp_path):
    dhan = FakeDhan()
    cache = str(tmp_path / "cache")
    df1 = load_candles(_instr(), "day", 30, dhan_client=dhan, cache_dir=cache)
    assert len(df1) == 1 and dhan.calls == 1
    # second call hits cache, no new fetch
    df2 = load_candles(_instr(), "day", 30, dhan_client=dhan, cache_dir=cache)
    assert dhan.calls == 1 and len(df2) == 1


def test_no_cache_no_client_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        load_candles(_instr(), "day", 30, dhan_client=None,
                     cache_dir=str(tmp_path / "empty"))
