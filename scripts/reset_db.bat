@echo off
REM ============================================================
REM Mnemosyne Database Reset Script
REM WARNING: This will DELETE all existing data!
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0\.."

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  ⚠️  DATABASE RESET - ALL DATA WILL BE DELETED!          ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo This will:
echo   1. Delete .mnemosyne/activity.db
echo   2. Delete all screenshots
echo   3. Clear Redis stream (mnemosyne:events)
echo   4. Recreate database with fresh schema
echo.

set /p CONFIRM="Type 'yes' to confirm: "
if /I not "%CONFIRM%"=="yes" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo [STEP 1/4] Deleting old database files...
if exist ".mnemosyne\activity.db" (
    del /f /q ".mnemosyne\activity.db" 2>nul
    echo   Deleted: activity.db
)
if exist ".mnemosyne\activity.db-shm" (
    del /f /q ".mnemosyne\activity.db-shm" 2>nul
    echo   Deleted: activity.db-shm
)
if exist ".mnemosyne\activity.db-wal" (
    del /f /q ".mnemosyne\activity.db-wal" 2>nul
    echo   Deleted: activity.db-wal
)

echo.
echo [STEP 2/4] Cleaning screenshots directory...
if exist "screenshots" (
    del /f /q "screenshots\*.png" 2>nul
    echo   Cleaned screenshots folder
) else (
    mkdir screenshots
    echo   Created screenshots folder
)

echo.
echo [STEP 3/4] Clearing Redis stream...
where redis-cli >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    redis-cli DEL mnemosyne:events >nul 2>nul
    redis-cli XGROUP DESTROY mnemosyne:events brain_processors >nul 2>nul
    echo   Cleared Redis stream and consumer group
) else (
    echo   Redis CLI not found - skipping (clear manually if needed)
)

echo.
echo [STEP 4/4] Creating fresh database with schema...

REM Ensure .mnemosyne directory exists
if not exist ".mnemosyne" mkdir ".mnemosyne"

REM Run Python script to create database
.venv\Scripts\python.exe scripts\init_db.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to create database!
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  ✅ DATABASE RESET COMPLETE!                             ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo Next steps:
echo   1. Start Watcher: scripts\run_watcher.bat
echo   2. Start Brain:   scripts\brain_v4.bat
echo.
pause
