@echo off
REM ============================================================
REM Mnemosyne Core V3.0 - Build Watcher
REM ============================================================
chcp 65001 >nul

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  🔨 Building Mnemosyne Watcher                           ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0\.."

REM Check Go installation
where go >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Go is not installed or not in PATH!
    echo Install from: https://go.dev/dl/
    pause
    exit /b 1
)

echo [INFO] Go version:
go version
echo.

REM Download dependencies
echo [INFO] Downloading dependencies...
go mod download
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download dependencies!
    pause
    exit /b 1
)

REM Build watcher
echo [INFO] Building watcher.exe...
go build -ldflags="-s -w" -o watcher.exe ./cmd/watcher
if %errorlevel% neq 0 (
    echo [ERROR] Build failed!
    pause  
    exit /b 1
)

echo.
echo [SUCCESS] watcher.exe built successfully!
echo [INFO] Size: 
dir watcher.exe | findstr /C:"watcher.exe"
echo.
echo [USAGE] Run: watcher.exe -db .mnemosyne/activity.db
echo.
pause
