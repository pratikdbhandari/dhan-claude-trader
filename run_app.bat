@echo off
REM ============================================================
REM  Dhan-Claude Trader launcher (Windows)
REM  Double-click to start the dashboard at http://localhost:8501
REM ============================================================
cd /d "%~dp0"
echo Starting Dhan-Claude Trader...
python -m streamlit run app.py --server.port 8501
pause
