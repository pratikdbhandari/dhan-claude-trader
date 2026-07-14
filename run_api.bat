@echo off
REM ============================================================
REM  Dhan-Claude Trader API launcher (Windows)
REM  Serves the FastAPI layer at http://localhost:8000 for the
REM  phone app (via a Cloudflare Tunnel pointed at this port).
REM  Run this ALONGSIDE run_app.bat, not instead of it.
REM ============================================================
cd /d "%~dp0"
echo Starting Dhan-Claude Trader API...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
pause
