# Dashboard Reface Design — "Terminal" Hybrid

**Date:** 2026-07-14
**Status:** Approved
**Depends on:** `ui/themes.py` (token themes + `css()`/`apply()`), `app.py` (dashboard render), `tests/test_ui_themes.py`.
**Last of the original 4-feature sequence** (desktop ✓, bell ✓, BTST ✓, reface).

---

## 1. Purpose

Give the dashboard a new face: a dark, dense "terminal" look with **large, bold key
numbers** (P&L, confidence) — the hybrid direction the user picked from the mockups.
Delivered as (a) a new `terminal` theme in the existing switcher and (b) structural
component upgrades (metric tiles, accent-bordered signal cards, big-number emphasis)
that all themes inherit, colored by each theme's tokens.

**Principles kept:** themes still differ by color tokens; the *structural* CSS is shared
across themes (a card looks structurally the same in every theme, just recolored). The
existing 5 themes keep working. `app.py` stays a thin render layer; `css()` stays a pure
string builder.

**Out of scope:** refacing the other pages (Reports/Screener/Options/Settings/GoLive/BTST)
beyond what they inherit for free from the shared CSS; new charts; behavior changes.

---

## 2. Two parts

### Part A — `ui/themes.py` (unit-testable)
1. Add a `terminal` token set to `THEMES` (dark hybrid palette): near-black bg, panel
   surface, hairline border, light ink, muted gray, teal accent, dark sidebar.
2. Add shared **component CSS** to `css()` that every theme gets, driven by existing
   tokens (`--bg`, `--surface`, `--border`, `--ink`, `--muted`, `--green`, `--signal`,
   `--gold`, `--klein`):
   - `.metric-tile` — surface bg, 8px radius, small uppercase muted label + `.metric-num`
     (≈24px, weight 500).
   - `.signal-card` — surface bg with a 3px left border; modifier classes
     `.signal-card.buy` (green left border), `.signal-card.sell` (red), `.signal-card.hold`
     (gold).
   - `.conf-num` — large (≈22px, weight 500) confidence figure, colored by buy/sell/hold.
   - `.chip` tweaks already exist; reuse.
   These are additive; existing classes (`.card`, `.buy`, `.sell`, `.pnl-pos`, etc.) stay.

`css(name)` remains a pure function returning a `<style>` string; `THEME_NAMES` gains
`"terminal"` so the sidebar picker lists it.

### Part B — `app.py` dashboard markup (manual-verify)
Rework the dashboard's four regions to use the new classes, matching the approved mockup:
- **Metric row** (Today P&L / Loss buffer / Open positions / Orders) → 4 `.metric-tile`s
  with `.metric-num`, P&L colored by sign.
- **Signal cards** → `.signal-card.{buy|sell|hold}` with the confidence rendered via
  `.conf-num`; keep entry/SL/target line, provider chips, quality chip, Select button.
- **Open positions** and a compact **BTST book** peek → two side-by-side tiles at the
  bottom (BTST peek reuses `open_btst_book`, read-only here; full management stays on the
  BTST page).
No logic changes — same `signal_engine`/`risk_manager`/`trade_controller` calls, same
two-step confirm, same data. Only the HTML/CSS the values are rendered into changes.

---

## 3. Data flow

Unchanged. The reface is presentation-only: the same objects (`ConsensusSignal`,
`RiskCheck`, positions, `open_btst_book`) render into new markup + classes. `apply()`
still injects `css(active_theme)` and the sidebar picker.

---

## 4. Error / edge handling

- New theme is just another token set — a missing/renamed token would surface at
  `css()` build; covered by the themes test asserting the terminal set has every key.
- All-theme structural CSS uses only tokens that already exist in every theme dict, so
  no theme renders an undefined variable.
- `app.py` markup changes are guarded by the existing DhanError/HOLD/empty handling
  already in the dashboard (kept intact).

---

## 5. Testing

- `tests/test_ui_themes.py` (extend): `"terminal"` in `THEME_NAMES`; the `terminal`
  token dict has the same keys as `aura` (no missing token); `css("terminal")` returns a
  non-empty `<style>` containing the new component classes (`.metric-tile`, `.metric-num`,
  `.signal-card`, `.conf-num`); `css()` still works for every existing theme; the shared
  component classes appear regardless of theme name.
- `app.py` dashboard = manual verification (run `streamlit run app.py`, eyeball the four
  regions in the `terminal` theme and confirm existing themes still render): it's the
  render layer, unit-untested by existing convention.
