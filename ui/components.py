"""Reusable on-design-system HTML snippets (Swiss / AURA). Each returns an HTML
string for st.markdown(..., unsafe_allow_html=True). Pure + testable."""
from __future__ import annotations

_CHIP_CLASS = {"blue": "chip-blue", "green": "chip-green", "gold": "chip-gold",
               "red": "chip-red"}


def eyebrow(text: str) -> str:
    return f"<div class='eyebrow'>{text}</div>"


def page_header(eyebrow_text: str, title: str, desc: str = "") -> str:
    html = (f"<div class='eyebrow'>{eyebrow_text}</div>"
            f"<div class='page-title'>{title}</div>")
    if desc:
        html += f"<div class='page-desc'>{desc}</div>"
    return html


def chip(text: str, kind: str = "blue") -> str:
    cls = _CHIP_CLASS.get(kind, "chip-blue")
    return f"<span class='chip {cls}'>{text}</span>"


def signal_chip(signal: str) -> str:
    """Map a BUY/SELL/HOLD signal to a meaning-coloured chip."""
    kind = {"BUY": "green", "SELL": "red", "HOLD": "gold"}.get(signal.upper(), "blue")
    return chip(signal, kind)
