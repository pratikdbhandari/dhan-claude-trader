from ui import themes


def test_chart_colors_has_all_keys():
    c = themes.chart_colors()
    for k in ("bg", "ink", "grid", "green", "signal", "gold", "accent"):
        assert k in c


def test_chart_colors_falls_back_to_aura_without_streamlit():
    c = themes.chart_colors()
    assert c["bg"] == themes.THEMES["aura"]["bg"]
    assert c["green"] == themes.GREEN and c["signal"] == themes.SIGNAL
