@echo off
REM ============================================================
REM  DhanTrader.exe builder - run from the repo root.
REM  Output: dist\DhanTrader\DhanTrader.exe
REM ============================================================
cd /d "%~dp0"
echo Installing build requirements...
pip install -r requirements.txt -r requirements-desktop.txt || goto :fail
echo Building (this takes several minutes)...
pyinstaller desktop\build.spec --noconfirm || goto :fail
echo.
echo Build OK: dist\DhanTrader\DhanTrader.exe
pause
exit /b 0
:fail
echo BUILD FAILED - read the error above.
pause
exit /b 1
