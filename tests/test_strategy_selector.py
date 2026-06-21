from services.market_context import MarketContext
from services.strategy_selector import select


def _ctx(regime="TRENDING", vix=14.0, rsi=50.0, rsi_state="NEUTRAL", events=None):
    return MarketContext(regime=regime, vix=vix, index_rsi=rsi, rsi_state=rsi_state,
                         headlines=[], event_flags=events or [])


def test_trending_low_vix_picks_momentum():
    sel = select(_ctx("TRENDING", vix=13))
    assert sel.preset == "intraday_momentum"
    assert any("positional_quality" in n for n in sel.extra_notes)


def test_trending_high_vix_warns_size_down():
    sel = select(_ctx("TRENDING", vix=22))
    assert sel.preset == "intraday_momentum"
    assert any("size down" in c for c in sel.cautions)


def test_ranging_picks_scalper():
    assert select(_ctx("RANGING", vix=16)).preset == "range_scalper"


def test_oversold_picks_reversion():
    sel = select(_ctx("TRENDING", vix=16, rsi=22, rsi_state="OVERSOLD"))
    assert sel.preset == "range_scalper"
    assert any("mean-reversion long" in r for r in sel.reasons)


def test_volatile_or_very_high_vix_cautions():
    sel = select(_ctx("VOLATILE", vix=28))
    assert sel.preset == "range_scalper"
    assert any("volatility" in c.lower() for c in sel.cautions)


def test_unknown_regime_conservative():
    sel = select(_ctx("UNKNOWN", vix=None, rsi=None, rsi_state="UNKNOWN"))
    assert sel.preset == "range_scalper"
    assert any("unknown" in c.lower() for c in sel.cautions)


def test_event_flags_append_cautions():
    sel = select(_ctx("TRENDING", vix=14, events=["EXPIRY", "RBI"]))
    text = " ".join(sel.cautions)
    assert "Expiry" in text and "Policy" in text
