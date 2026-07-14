"""Serialize a Plotly figure to JSON for the template. app.js parses the embedded
JSON and calls Plotly.newPlot client-side (Plotly.js is vendored in static/)."""
from __future__ import annotations
import plotly.io as pio


def fig_json(fig) -> str:
    return pio.to_json(fig)
