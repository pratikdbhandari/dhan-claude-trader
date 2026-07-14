@echo off
cd /d "%~dp0"
echo Starting Dhan-Claude Trader (HTML)...
python -m uvicorn web.server:app --host 127.0.0.1 --port 8501
pause
