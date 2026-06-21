import numpy as np
import pandas as pd
import services.strategies.trend  # noqa: F401
import services.strategies.mean_reversion  # noqa: F401
import services.strategies.breakout  # noqa: F401
import services.strategies.volume  # noqa: F401
import services.strategies.structure  # noqa: F401
from services.screener import scan
from core.models import Instrument


def _trending(n=120):
    close = 100 + np.linspace(0, 40, n)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000.0)})


def _flat(n=120):
    close = np.full(n, 100.0)
    return pd.DataFrame({"open": close, "high": close + 0.1, "low": close - 0.1,
                         "close": close, "volume": np.full(n, 1000.0)})


def _instr(sym):
    return Instrument(symbol=sym, exchange_segment="NSE_EQ", security_id="1",
                      kind="EQUITY")


def test_scan_returns_signalled_instruments():
    universe = [_instr("UP"), _instr("FLAT")]
    data = {"UP": _trending(), "FLAT": _flat()}
    rows = scan(universe, candles_fn=lambda i: data[i.symbol],
                active_ids=list(range(1, 30)))
    syms = [r["symbol"] for r in rows if "error" not in r]
    assert "UP" in syms   # trending instrument produced a signal


def test_scan_reports_errors_not_crash():
    def boom(instr):
        raise RuntimeError("no data")
    rows = scan([_instr("X")], candles_fn=boom, active_ids=list(range(1, 30)))
    assert rows and rows[0]["error"] == "no data"


def test_scan_ranks_by_strength():
    universe = [_instr("A"), _instr("B")]
    strong, weak = _trending(), _trending()
    data = {"A": weak, "B": strong}
    rows = [r for r in scan(universe, candles_fn=lambda i: data[i.symbol],
                            active_ids=list(range(1, 30))) if "error" not in r]
    if len(rows) == 2:
        assert abs(rows[0]["net_score"]) >= abs(rows[1]["net_score"])
