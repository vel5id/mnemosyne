@echo off
REM ============================================================
REM Mnemosyne Database Maintenance Script
REM Phase 7: Storage Optimization
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0\.."

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  🔧 Running Database Maintenance                         ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    pause
    exit /b 1
)

echo [INFO] Running full maintenance cycle...
echo [INFO] - Pruning old sessions (30+ days)
echo [INFO] - Pruning old raw_events (7+ days)
echo [INFO] - Cleaning orphaned screenshots
echo [INFO] - Running VACUUM
echo.

.venv\Scripts\python.exe -m core.dal.maintenance

echo.
echo [DONE] Maintenance complete!
pause
