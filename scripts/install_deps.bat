@echo off
echo Installing dependencies (latest)...
go get github.com/kbinani/screenshot@latest
if %errorlevel% neq 0 (
    echo Failed to get screenshot lib
    exit /b %errorlevel%
)
echo Success
go mod tidy
