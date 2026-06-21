from services import indicators as ind

def test_rsi_bounds(trending_candles):
    rsi = ind.rsi(trending_candles["close"])
    last = rsi.dropna().iloc[-1]
    assert 0 <= last <= 100
    assert last > 50

def test_atr_positive(trending_candles):
    atr = ind.atr(trending_candles)
    assert atr.dropna().iloc[-1] > 0

def test_adx_high_in_trend(trending_candles):
    assert ind.adx(trending_candles).dropna().iloc[-1] > 20
