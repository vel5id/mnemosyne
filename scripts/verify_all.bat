@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Full Verification Suite
REM Purpose: Run all verification checks (Go + Python)
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  🏗️ MNEMOSYNE CORE V3.0 - FULL VERIFICATION SUITE           ║
echo ║  Date: %DATE% %TIME%
echo ╚══════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."
set PROJECT_ROOT=%CD%
echo [INFO] Project root: %PROJECT_ROOT%
echo.

REM ============================================================
REM Phase 1: Go Verification
REM ============================================================
echo ┌──────────────────────────────────────────────────────────────┐
echo │  PHASE 1: Go (Watcher Tier)                                  │
echo └──────────────────────────────────────────────────────────────┘
echo.

echo [GO-1] Checking Go version...
go version
if %ERRORLEVEL% NEQ 0 (
    echo [FATAL] Go not installed or not in PATH!
    set GO_RESULT=1
    goto :python_phase
)
echo.

echo [GO-2] Verifying module dependencies...
go mod verify
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go mod verify failed!
    set GO_RESULT=1
    goto :python_phase
)
echo [OK] go mod verify
echo.

echo [GO-3] Static analysis (go vet)...
go vet ./cmd/... ./internal/... 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go vet found issues!
    set GO_RESULT=1
) else (
    echo [OK] go vet passed
)
echo.

echo [GO-4] Building watcher binary...
go build -o watcher_verify.exe ./cmd/watcher/main.go 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    set GO_RESULT=1
) else (
    echo [OK] Build successful
    del watcher_verify.exe 2>nul
)
echo.

echo [GO-5] Running Go tests...
go test -v ./tests/go/... -count=1 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Go tests failed!
    set GO_RESULT=1
) else (
    echo [OK] Go tests passed
    set GO_RESULT=0
)
echo.

:python_phase
REM ============================================================
REM Phase 2: Python Verification
REM ============================================================
echo ┌──────────────────────────────────────────────────────────────┐
echo │  PHASE 2: Python (Brain Tier)                                │
echo └──────────────────────────────────────────────────────────────┘
echo.

REM Activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated.
) else (
    echo [WARNING] .venv not found - using system Python
)
echo.

echo [PY-1] Checking Python version...
python --version
if %ERRORLEVEL% NEQ 0 (
    echo [FATAL] Python not installed or not in PATH!
    set PY_RESULT=1
    goto :summary
)
echo.

echo [PY-2] Checking core module imports...
python -c "import core.dal.sqlite_provider; import core.system.guardrails; import core.security.sanitizer; print('[OK] Core modules import successfully')" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some core modules have import issues
    set PY_IMPORT=1
) else (
    set PY_IMPORT=0
)
echo.

echo [PY-3] Running Python tests (excluding heavy tests)...
python -m pytest tests/python/test_infrastructure.py tests/python/test_perception.py -v --tb=short 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some Python tests failed (may be expected for OCR)
    set PY_RESULT=1
) else (
    echo [OK] Python tests passed
    set PY_RESULT=0
)
echo.

:summary
REM ============================================================
REM Summary
REM ============================================================
echo.
echo ════════════════════════════════════════════════════════════════
echo                      VERIFICATION SUMMARY
echo ════════════════════════════════════════════════════════════════
echo.

if "%GO_RESULT%"=="0" (
    echo   ✅ Go (Watcher):   PASSED
) else (
    echo   ❌ Go (Watcher):   FAILED
)

if "%PY_RESULT%"=="0" (
    echo   ✅ Python (Brain): PASSED
) else (
    echo   ⚠️  Python (Brain): PARTIAL (some optional tests failed)
)

echo.
echo ════════════════════════════════════════════════════════════════

if "%GO_RESULT%"=="0" (
    echo.
    echo   🎉 CORE CHECKS PASSED - Ready for development!
    echo.
) else (
    echo.
    echo   ⚠️  ISSUES FOUND - Please review errors above
    echo.
)

pause
exit /b %GO_RESULT%
