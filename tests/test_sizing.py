from services.sizing import quality_multiplier, sized_qty, MAX_MULTIPLIER


def test_below_threshold_skips():
    assert quality_multiplier(40) == 0.0
    assert sized_qty(100, 40) == 0


def test_bands_scale_up_with_quality():
    assert quality_multiplier(55) == 0.5
    assert quality_multiplier(70) == 1.0
    assert quality_multiplier(85) == MAX_MULTIPLIER


def test_profit_probability_trims_low_history():
    # strong quality but historically losing bucket => trimmed
    assert quality_multiplier(70, profit_probability=40) == 0.5


def test_profit_probability_boosts_high_history_capped():
    m = quality_multiplier(70, profit_probability=70)
    assert m <= MAX_MULTIPLIER and m > 1.0


def test_sized_qty_scales_base():
    assert sized_qty(100, 85) == 125     # 100 * 1.25
    assert sized_qty(100, 70) == 100
    assert sized_qty(100, 55) == 50
