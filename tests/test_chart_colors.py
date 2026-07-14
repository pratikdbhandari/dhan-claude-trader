from ui import themes


def test_chart_colors_has_all_keys():
    c = themes.chart_colors()
    for k in ("bg", "ink", "grid", "green", "signal", "gold", "accent"):
        assert k in c


def test_chart_colors_maps_active_theme_tokens(monkeypatch):
    # force a known active theme and assert the palette maps its tokens
    from core import config_store
    monkeypatch.setattr(config_store, "get_setting",
                        lambda key, default=None, **kw: "terminal" if key == "UI_THEME" else default)
    c = themes.chart_colors()
    assert c["bg"] == themes.THEMES["terminal"]["bg"]
    assert c["accent"] == themes.THEMES["terminal"]["accent"]
    assert c["green"] == themes.GREEN and c["signal"] == themes.SIGNAL


def test_chart_colors_unknown_theme_falls_back_to_aura(monkeypatch):
    from core import config_store
    monkeypatch.setattr(config_store, "get_setting",
                        lambda key, default=None, **kw: "does-not-exist")
    c = themes.chart_colors()
    assert c["bg"] == themes.THEMES["aura"]["bg"]
