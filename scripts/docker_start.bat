@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Docker Startup Script
REM ============================================================
chcp 65001 >nul
setlocal

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  🧠 MNEMOSYNE CORE V3.0 - Docker Startup                 ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."

REM Check if .env exists
if not exist ".env" (
    echo [WARN] .env file not found. Copying from .env.example...
    copy .env.example .env
    echo [INFO] Please edit .env with your settings.
    pause
)

REM Check Docker
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker not found! Please install Docker Desktop.
    pause
    exit /b 1
)

REM Check NVIDIA Docker runtime (optional)
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] NVIDIA GPU support detected.
) else (
    echo [WARN] NVIDIA GPU not available. VLM will run on CPU (slow).
)
echo.

REM Pull Ollama image
echo [STEP 1/3] Pulling Ollama image...
docker pull ollama/ollama:latest
echo.

REM Build Brain image
echo [STEP 2/3] Building Brain image...
docker compose build brain
echo.

REM Start services
echo [STEP 3/3] Starting services...
docker compose up -d
echo.

REM Show status
echo ════════════════════════════════════════════════════════════
docker compose ps
echo ════════════════════════════════════════════════════════════
echo.
echo [INFO] Services started. Ollama available at http://localhost:11434
echo [INFO] To view logs: docker compose logs -f
echo [INFO] To stop: docker compose down
echo.
pause
