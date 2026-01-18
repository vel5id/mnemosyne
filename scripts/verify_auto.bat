@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Full Verification Suite (No Pause)
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ========================================================
echo   MNEMOSYNE CORE V3.0 - FULL VERIFICATION
echo   Date: %DATE% %TIME%
echo ========================================================
echo.

cd /d "c:\Users\vladi\Downloads\Folders\Own code\Repositories\mnemosyne\test_windsurf"
set PROJECT_ROOT=%CD%
echo [INFO] Project root: %PROJECT_ROOT%
echo.

REM ============================================================
REM Phase 1: Go Verification
REM ============================================================
echo --------------------------------------------------------
echo   PHASE 1: Go (Watcher Tier)
echo --------------------------------------------------------
echo.

echo [GO-1] Go version:
go version
if %ERRORLEVEL% NEQ 0 (
    echo [FATAL] Go not installed!
    set GO_RESULT=1
    goto :python_phase
)
echo.

echo [GO-2] go mod verify...
go mod verify
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go mod verify failed!
    set GO_RESULT=1
) else (
    echo [OK] go mod verify
)
echo.

echo [GO-3] go vet...
go vet ./cmd/... ./internal/...
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go vet found issues!
    set GO_RESULT=1
) else (
    echo [OK] go vet passed
    set GO_RESULT=0
)
echo.

echo [GO-4] Building watcher...
go build -o watcher_verify.exe ./cmd/watcher/main.go
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    set GO_RESULT=1
) else (
    echo [OK] Build successful
    del watcher_verify.exe 2>nul
    set GO_RESULT=0
)
echo.

echo [GO-5] Running Go tests...
go test -v ./tests/go/... -count=1
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
echo --------------------------------------------------------
echo   PHASE 2: Python (Brain Tier)
echo --------------------------------------------------------
echo.

echo [PY-1] Python version:
python --version
if %ERRORLEVEL% NEQ 0 (
    echo [FATAL] Python not installed!
    set PY_RESULT=1
    goto :summary
)
echo.

echo [PY-2] Checking core module imports...
python -c "import core.dal.sqlite_provider; import core.system.guardrails; import core.security.sanitizer; print('[OK] Core modules import successfully')"
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some core modules have import issues
    set PY_RESULT=1
) else (
    set PY_RESULT=0
)
echo.

echo [PY-3] Running Python tests...
python -m pytest tests/python/ -v --tb=short
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python tests failed!
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
echo ========================================================
echo                   VERIFICATION SUMMARY
echo ========================================================
echo.

if "%GO_RESULT%"=="0" (
    echo   [PASS] Go Watcher
) else (
    echo   [FAIL] Go Watcher
)

if "%PY_RESULT%"=="0" (
    echo   [PASS] Python Brain
) else (
    echo   [FAIL] Python Brain
)

echo.
echo ========================================================
echo Done.
exit /b 0
