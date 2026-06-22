"""Theme system — Swiss / International Typographic design language ("AURA") plus
token-variant themes. Same structural rules everywhere (sharp corners, hairline
borders, no shadows, JetBrains Mono body, Outfit display); only color tokens differ.

css(name) returns a <style> block; apply() injects it + a sidebar theme picker that
persists the choice via config_store. Pure string-builder (unit-testable)."""
from __future__ import annotations

# token sets per theme: bg, surface, surface_hover, border, ink, muted, accent,
# sidebar_bg, sidebar_ink
THEMES: dict[str, dict] = {
    "aura": {
        "bg": "#FFFFFF", "surface": "#F9FAFB", "surface_hover": "#F3F4F6",
        "border": "#E5E7EB", "ink": "#0A0A0A", "muted": "#4B5563",
        "accent": "#002FA7", "sidebar_bg": "#0A0A0A", "sidebar_ink": "#E5E7EB",
    },
    "dark": {
        "bg": "#0b0f18", "surface": "#161d2e", "surface_hover": "#1c2436",
        "border": "#26314a", "ink": "#e8ecf5", "muted": "#9aa4b8",
        "accent": "#6366f1", "sidebar_bg": "#0A0A0A", "sidebar_ink": "#e8ecf5",
    },
    "light": {
        "bg": "#FFFFFF", "surface": "#F5F5F5", "surface_hover": "#ECECEC",
        "border": "#E0E0E0", "ink": "#111111", "muted": "#666666",
        "accent": "#002FA7", "sidebar_bg": "#1A1A1A", "sidebar_ink": "#EEEEEE",
    },
    "high_contrast": {
        "bg": "#000000", "surface": "#0A0A0A", "surface_hover": "#161616",
        "border": "#FFFFFF", "ink": "#FFFFFF", "muted": "#CCCCCC",
        "accent": "#FFD700", "sidebar_bg": "#000000", "sidebar_ink": "#FFFFFF",
    },
    "solarized": {
        "bg": "#FDF6E3", "surface": "#EEE8D5", "surface_hover": "#E4DCC4",
        "border": "#93A1A1", "ink": "#073642", "muted": "#586E75",
        "accent": "#268BD2", "sidebar_bg": "#002B36", "sidebar_ink": "#EEE8D5",
    },
}

# semantic colors — constant across themes (color only conveys meaning)
SIGNAL, GOLD, GREEN = "#FF2A2A", "#FFD700", "#059669"

THEME_NAMES = list(THEMES.keys())


def css(name: str) -> str:
    t = THEMES.get(name, THEMES["aura"])
    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:{t['bg']}; --surface:{t['surface']}; --surface-hover:{t['surface_hover']};
  --border:{t['border']}; --ink:{t['ink']}; --muted:{t['muted']};
  --klein:{t['accent']}; --signal:{SIGNAL}; --gold:{GOLD}; --green:{GREEN};
  --sidebar-bg:{t['sidebar_bg']}; --sidebar-ink:{t['sidebar_ink']};
}}
/* base */
.stApp {{ background:var(--bg); color:var(--ink); }}
html, body, [class*="css"], .stMarkdown, p, span, div, label, input, textarea,
.stSelectbox, .stNumberInput, button {{ font-family:'JetBrains Mono', monospace !important; }}
h1, h2, h3, h4 {{ font-family:'Outfit', sans-serif !important; font-weight:800 !important;
  letter-spacing:-0.02em; color:var(--ink); }}
* {{ border-radius:0 !important; box-shadow:none !important; }}
::selection {{ background:var(--klein); color:#fff; }}
::-webkit-scrollbar {{ width:10px; height:10px; }}
::-webkit-scrollbar-track {{ background:var(--surface); }}
::-webkit-scrollbar-thumb {{ background:#D1D5DB; }}

/* sidebar */
section[data-testid="stSidebar"] {{ background:var(--sidebar-bg); border-right:1px solid var(--border); }}
section[data-testid="stSidebar"] * {{ color:var(--sidebar-ink) !important; }}
section[data-testid="stSidebar"] a {{ color:var(--sidebar-ink) !important; }}
section[data-testid="stSidebar"] [aria-current="page"] {{
  background:var(--klein) !important; border-left:3px solid var(--gold) !important; }}

/* buttons: uppercase mono, sharp, 1px border, color transition */
.stButton > button {{
  font-family:'JetBrains Mono', monospace !important; text-transform:uppercase;
  font-weight:700; font-size:0.72rem; letter-spacing:0.08em; padding:0.55rem 1rem;
  background:var(--ink); color:var(--bg); border:1px solid var(--ink);
  transition:background .15s ease, color .15s ease; }}
.stButton > button:hover {{ background:var(--klein); color:#fff; border-color:var(--klein); }}
.stButton > button[kind="primary"] {{ background:var(--klein); color:#fff; border-color:var(--klein); }}
.stDownloadButton > button {{ text-transform:uppercase; font-weight:700; border:1px solid var(--ink); }}

/* cards & inputs = white box + hairline border, no shadow */
.card {{ background:var(--bg); border:1px solid var(--border); padding:14px 16px; margin-bottom:10px; }}
[data-testid="stMetric"], .stDataFrame, .stTable, .stExpander,
.stSelectbox div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  background:var(--surface); border:1px solid var(--border) !important; }}

/* eyebrow + headers */
.eyebrow {{ font-family:'JetBrains Mono', monospace; font-size:0.65rem; text-transform:uppercase;
  letter-spacing:0.2em; font-weight:700; color:var(--muted); }}
.page-title {{ font-family:'Outfit', sans-serif; font-weight:900; font-size:2.1rem;
  letter-spacing:-0.02em; color:var(--ink); margin:2px 0 2px; line-height:1.05; }}
.page-desc {{ color:var(--muted); font-size:0.85rem; }}

/* status chips */
.chip {{ display:inline-block; font-family:'JetBrains Mono', monospace; font-size:0.62rem;
  text-transform:uppercase; letter-spacing:0.06em; font-weight:700; padding:2px 8px;
  color:#fff; }}
.chip-blue {{ background:var(--klein); }} .chip-green {{ background:var(--green); }}
.chip-gold {{ background:var(--gold); color:#0A0A0A; }} .chip-red {{ background:var(--signal); }}

/* meaning text */
.buy, .pnl-pos {{ color:var(--green); font-weight:700; }}
.sell, .pnl-neg {{ color:var(--signal); font-weight:700; }}
.hold {{ color:var(--gold); font-weight:700; }}
.muted {{ color:var(--muted); font-size:0.85rem; }}

/* motion: fade-up + pulse */
@keyframes fadeUp {{ from {{ opacity:0; transform:translateY(12px); }} to {{ opacity:1; transform:none; }} }}
.card, [data-testid="stMetric"] {{ animation:fadeUp .5s cubic-bezier(.16,1,.3,1); }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:.3; }} }}
.live-dot {{ animation:pulse 1.4s ease-in-out infinite; }}
</style>
"""


def apply(default: str = "aura") -> str:
    """Inject the active theme + a sidebar picker. Returns the active theme name."""
    import streamlit as st
    from core import config_store
    current = st.session_state.get("ui_theme") or config_store.get_setting("UI_THEME", default)
    if current not in THEMES:
        current = default
    st.markdown(css(current), unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("<div class='eyebrow'>APPEARANCE</div>", unsafe_allow_html=True)
        picked = st.selectbox("Theme", THEME_NAMES,
                              index=THEME_NAMES.index(current), key="ui_theme_pick",
                              label_visibility="collapsed")
        if picked != current:
            config_store.save({"UI_THEME": picked})
            st.session_state["ui_theme"] = picked
            st.rerun()
    return current
