from services import fundamentals

class FakeTicker:
    def __init__(self, info): self.info = info

def test_extracts_key_fundamentals():
    fac = lambda sym: FakeTicker({"trailingPE": 25.3, "trailingEps": 88.0,
                                  "marketCap": 1e12})
    out = fundamentals.get_fundamentals("RELIANCE", ticker_factory=fac)
    assert out["pe"] == 25.3 and out["eps"] == 88.0
    assert out["market_cap"] == 1e12

def test_error_returns_empty():
    def boom(sym): raise RuntimeError("yf down")
    assert fundamentals.get_fundamentals("X", ticker_factory=boom) == {}
