@echo off
REM ============================================================
REM Mnemosyne Brain - Local Launch (Native Python)
REM ============================================================
REM Run Brain locally for proper SQLite access
REM (Docker Brain can't write due to WAL file sharing issues)
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0\.."

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  🧠 Starting Mnemosyne Brain (Local Mode)                ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] Virtual environment not found!
    echo Run: uv venv && uv pip install -r requirements.txt
    pause
    exit /b 1
)

REM Set environment variables
set MNEMOSYNE_DB_PATH=.mnemosyne/activity.db
set OLLAMA_VLM_HOST=http://localhost:11434
set OLLAMA_LLM_HOST=http://localhost:11435
set VLM_MODEL=minicpm-v
set LLM_MODEL_HEAVY=deepseek-r1:1.5b
set LOG_LEVEL=INFO

echo [INFO] DB Path: %MNEMOSYNE_DB_PATH%
echo [INFO] VLM Host: %OLLAMA_VLM_HOST%
echo [INFO] LLM Host: %OLLAMA_LLM_HOST%
echo.

REM Start Brain
python main.py
