@echo off
echo Starting Mnemosyne Brain v4.0 (Redis Mode)...
set MNEMOSYNE_REDIS_HOST=localhost
set OLLAMA_LLM_HOST=http://localhost:11435
set OLLAMA_VLM_HOST=http://localhost:11436

REM Запускаем Python напрямую из виртуального окружения
.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Mnemosyne crashed. Press any key to exit.
    pause
)