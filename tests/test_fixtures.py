def test_trending_fixture_rises(trending_candles):
    assert trending_candles["close"].iloc[-1] > trending_candles["close"].iloc[0]
    assert set(["open","high","low","close","volume"]).issubset(trending_candles.columns)

def test_ranging_fixture_oscillates(ranging_candles):
    c = ranging_candles["close"]
    assert c.max() - c.min() < c.mean() * 0.1
    assert len(ranging_candles) >= 200
