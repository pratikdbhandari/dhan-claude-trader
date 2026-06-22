from ui import themes, components


def test_all_themes_produce_css_with_tokens():
    for name in themes.THEME_NAMES:
        block = themes.css(name)
        assert "JetBrains Mono" in block and "Outfit" in block
        assert "border-radius:0" in block
        assert themes.THEMES[name]["accent"] in block


def test_unknown_theme_falls_back_to_aura():
    assert themes.css("nope") == themes.css("aura")


def test_expected_themes_present():
    assert {"aura", "dark", "light", "high_contrast", "solarized"} <= set(themes.THEME_NAMES)


def test_components_emit_html():
    assert "eyebrow" in components.eyebrow("LIVE")
    h = components.page_header("DASHBOARD", "Signals", "today")
    assert "page-title" in h and "Signals" in h and "today" in h


def test_signal_chip_colours():
    assert "chip-green" in components.signal_chip("BUY")
    assert "chip-red" in components.signal_chip("SELL")
    assert "chip-gold" in components.signal_chip("HOLD")
