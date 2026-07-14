# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DhanTrader.exe. Build from repo root:
    pyinstaller desktop/build.spec --noconfirm
Output: dist/DhanTrader/DhanTrader.exe (onedir; user data lives in data/ next
to the exe, created on first run by the launcher)."""
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Streamlit loads modules dynamically and reads its own dist metadata.
for pkg in ("streamlit", "altair", "pydeck"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:  # pkg not installed (streamlit extras) — skip
        print(f"build.spec: skipping collect_all({pkg!r}): {e}")

# Libraries imported dynamically by the app's services
hiddenimports += [
    "dhanhq", "ta", "plotly", "yfinance", "dotenv",
    "services.strategies.trend", "services.strategies.mean_reversion",
    "services.strategies.breakout", "services.strategies.volume",
    "services.strategies.structure",
    "uvicorn", "web.server", "web.deps", "web.charts",
    "web.routes.dashboard", "web.routes.reports", "web.routes.screener",
    "web.routes.backtest", "web.routes.options", "web.routes.settings",
    "web.routes.golive", "web.routes.btst",
]
for pkg in ("plotly", "ta", "yfinance", "dhanhq"):
    try:
        datas += copy_metadata(pkg, recursive=True)
    except Exception as e:
        print(f"build.spec: skipping copy_metadata({pkg!r}): {e}")

# The app's own source tree + default configs, unpacked to sys._MEIPASS
datas += [
    ("../app.py", "."),
    ("../pages", "pages"),
    ("../core", "core"),
    ("../services", "services"),
    ("../data/__init__.py", "data"),
    ("../data/journal.py", "data"),
    ("../data/segments.py", "data"),
    ("../ui", "ui"),
    ("../watchlist.json", "."),
    ("../strategies.json", "."),
    ("../providers.json", "."),
    ("../charges.json", "."),
    ("../costs.json", "."),
    ("../web/__init__.py", "web"),
    ("../web/server.py", "web"),
    ("../web/deps.py", "web"),
    ("../web/charts.py", "web"),
    ("../web/routes", "web/routes"),
    ("../web/templates", "web/templates"),
    ("../web/static", "web/static"),
]

a = Analysis(
    ["launcher.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DhanTrader",
    console=False,               # no console window
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DhanTrader")
