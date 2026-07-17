@echo off
REM ============================================================
REM  Stop the Dhan-Claude Trader web app.
REM  Needed because run_web_hidden.vbs leaves no console window
REM  to Ctrl+C. Kills whatever is LISTENING on port 8501.
REM ============================================================
setlocal
set FOUND=0

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    if not errorlevel 1 (
        echo Stopped the trading app ^(process %%p^).
        set FOUND=1
    )
)

if "%FOUND%"=="0" echo The trading app was not running on port 8501.
REM full path: a bare "timeout" can resolve to a non-Windows one earlier in PATH
"%SystemRoot%\System32\timeout.exe" /t 3 /nobreak >nul 2>&1
