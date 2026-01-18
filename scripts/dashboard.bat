@echo off
setlocal

echo ╔══════════════════════════════════════════════════════════╗
echo ║  📊 Starting Mnemosyne Observability Dashboard           ║
echo ╚══════════════════════════════════════════════════════════╝

cd /d "%~dp0\.."

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found. Trying global python...
)

REM Set Redis Host for v4.0 metrics
set MNEMOSYNE_REDIS_HOST=localhost

REM Run Dashboard
python status_dashboard.py
