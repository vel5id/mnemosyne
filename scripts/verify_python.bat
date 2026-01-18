@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Python Verification Script (venv)
REM Purpose: Verify Python modules (Brain tier) using venv
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  📐 AXIOM: Python Codebase Verification                  ║
echo ╠══════════════════════════════════════════════════════════╣
echo ║  1. Activate venv                                        ║
echo ║  2. Check Python version                                 ║
echo ║  3. Verify core module imports                           ║
echo ║  4. Run Python tests                                     ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."
echo [INFO] Working directory: %CD%
echo.

REM ============================================================
REM Step 1: Activate venv
REM ============================================================
echo [STEP 1/4] Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated.
) else (
    echo [ERROR] .venv not found! Run: uv venv .venv
    goto :error
)
echo.

REM ============================================================
REM Step 2: Check Python version
REM ============================================================
echo [STEP 2/4] Checking Python version...
python --version
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found!
    goto :error
)
echo.

REM ============================================================
REM Step 3: Verify core module imports
REM ============================================================
echo [STEP 3/4] Verifying core module imports...

echo   - core.dal.sqlite_provider
python -c "import core.dal.sqlite_provider" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] core.dal.sqlite_provider has import errors!
    goto :error
)

echo   - core.system.guardrails
python -c "import core.system.guardrails" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] core.system.guardrails has import errors!
    goto :error
)

echo   - core.security.sanitizer
python -c "import core.security.sanitizer" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] core.security.sanitizer has import errors!
    goto :error
)

echo [OK] Core modules import successfully.
echo.

REM ============================================================
REM Step 4: Run pytest (excluding heavy tests)
REM ============================================================
echo [STEP 4/4] Running Python tests...
echo   NOTE: Excluding test_cognition.py (requires torch)
python -m pytest tests/python/test_infrastructure.py tests/python/test_perception.py -v --tb=short 2>&1
set TEST_RESULT=%ERRORLEVEL%

echo.
echo ════════════════════════════════════════════════════════════
if %TEST_RESULT% EQU 0 (
    echo ✅ ALL PYTHON CHECKS PASSED
) else (
    echo ⚠️  SOME TESTS FAILED (exit code: %TEST_RESULT%)
    echo    See failures above - may be expected for OCR tests
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
