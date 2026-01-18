@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Docker Stop Script
REM ============================================================
chcp 65001 >nul

echo.
echo [INFO] Stopping Mnemosyne Docker services...
cd /d "%~dp0\.."

docker compose down

echo [OK] Services stopped.
pause
