@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Go Verification Script
REM Purpose: Build and test Go modules (Watcher tier)
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  📐 AXIOM: Go Codebase Verification                      ║
echo ╠══════════════════════════════════════════════════════════╣
echo ║  1. go mod verify                                        ║
echo ║  2. go vet ./...                                         ║
echo ║  3. go build cmd/watcher                                 ║
echo ║  4. go test ./tests/go/...                               ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."
echo [INFO] Working directory: %CD%
echo.

REM ============================================================
REM Step 1: Verify go.mod integrity
REM ============================================================
echo [STEP 1/4] Verifying go.mod dependencies...
go mod verify
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go mod verify failed!
    goto :error
)
echo [OK] Dependencies verified.
echo.

REM ============================================================
REM Step 2: Static analysis with go vet
REM ============================================================
echo [STEP 2/4] Running static analysis (go vet)...
go vet ./cmd/... ./internal/...
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] go vet found issues!
    goto :error
)
echo [OK] Static analysis passed.
echo.

REM ============================================================
REM Step 3: Build the Watcher binary
REM ============================================================
echo [STEP 3/4] Building watcher.exe...
go build -o watcher_test.exe ./cmd/watcher/main.go
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed!
    goto :error
)
echo [OK] Build successful: watcher_test.exe
del watcher_test.exe 2>nul
echo.

REM ============================================================
REM Step 4: Run Go tests
REM ============================================================
echo [STEP 4/4] Running Go tests...
go test -v ./tests/go/... -count=1
set TEST_RESULT=%ERRORLEVEL%

echo.
echo ════════════════════════════════════════════════════════════
if %TEST_RESULT% EQU 0 (
    echo ✅ ALL GO CHECKS PASSED
) else (
    echo ❌ SOME TESTS FAILED (exit code: %TEST_RESULT%)
)
echo ════════════════════════════════════════════════════════════
echo.
goto :end

:error
echo.
echo ════════════════════════════════════════════════════════════
echo ❌ VERIFICATION FAILED - See errors above
echo ════════════════════════════════════════════════════════════
exit /b 1

:end
pause
exit /b %TEST_RESULT%
