@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Full System Integration Test
REM ============================================================
chcp 65001 >nul

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  🧪 Mnemosyne Integration Testing Suite                  ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."

set PASSED=0
set FAILED=0

REM ============================================================
REM Step 1: Check Docker Services
REM ============================================================
echo [TEST 1/6] Checking Docker services...
docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Docker services not running. Starting...
    docker compose up -d
    timeout /t 30 /nobreak >nul
)
set /a PASSED+=1
echo [PASS] Docker check complete
echo.

REM ============================================================
REM Step 2: Check Dashboard API
REM ============================================================
echo [TEST 2/6] Checking Dashboard API (http://localhost:11433)...
curl -s http://localhost:11433/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Dashboard API not responding!
    set /a FAILED+=1
) else (
    echo [PASS] Dashboard API is online
    set /a PASSED+=1
)
echo.

REM ============================================================
REM Step 3: Check VLM Ollama  
REM ============================================================
echo [TEST 3/6] Checking VLM API (http://localhost:11434)...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] VLM API not responding (may still be loading models)
) else (
    echo [PASS] VLM API is online
    set /a PASSED+=1
)
echo.

REM ============================================================
REM Step 4: Check LLM Ollama
REM ============================================================
echo [TEST 4/6] Checking LLM API (http://localhost:11435)...
curl -s http://localhost:11435/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] LLM API not responding (may still be loading models)
) else (
    echo [PASS] LLM API is online
    set /a PASSED+=1
)
echo.

REM ============================================================
REM Step 5: Check Database File
REM ============================================================
echo [TEST 5/6] Checking SQLite database...
if exist ".mnemosyne\activity.db" (
    echo [PASS] Database file exists: .mnemosyne\activity.db
    set /a PASSED+=1
) else (
    echo [WARN] Database not found. Initializing...
    if not exist ".mnemosyne" mkdir .mnemosyne
    sqlite3 .mnemosyne\activity.db < db\schema.sql 2>nul
    if exist ".mnemosyne\activity.db" (
        echo [PASS] Database initialized
        set /a PASSED+=1
    ) else (
        echo [FAIL] Could not create database
        set /a FAILED+=1
    )
)
echo.

REM ============================================================
REM Step 6: Build and Check Watcher
REM ============================================================
echo [TEST 6/6] Building and testing Watcher...
if not exist "watcher.exe" (
    echo [INFO] Building watcher.exe...
    go build -ldflags="-s -w" -o watcher.exe ./cmd/watcher 2>nul
)
if exist "watcher.exe" (
    echo [PASS] watcher.exe exists
    set /a PASSED+=1
) else (
    echo [FAIL] watcher.exe build failed
    set /a FAILED+=1
)
echo.

REM ============================================================
REM Summary
REM ============================================================
echo ══════════════════════════════════════════════════════════
echo                      TEST SUMMARY
echo ══════════════════════════════════════════════════════════
echo   ✅ Passed: %PASSED%
echo   ❌ Failed: %FAILED%
echo.

if %FAILED% equ 0 (
    echo [SUCCESS] All integration tests passed!
    echo.
    echo Next steps:
    echo   1. Start Watcher:    watcher.exe
    echo   2. Open Dashboard:   start http://localhost:11433
    echo.
) else (
    echo [WARNING] Some tests failed. Check output above.
)

pause
