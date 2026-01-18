@echo off
REM ============================================================
REM Mnemosyne Watcher - Launch Script (v4.0 Redis Mode)
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0\.."

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  👁️ Starting Mnemosyne Watcher (Redis Mode)              ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

if not exist "watcher.exe" (
    echo [ERROR] watcher.exe not found!
    echo Run: scripts\build_watcher.bat
    pause
    exit /b 1
)

echo [INFO] Connecting to Redis at localhost:6379...
echo [INFO] Press Ctrl+C to stop.
echo.

watcher.exe -redis localhost:6379

