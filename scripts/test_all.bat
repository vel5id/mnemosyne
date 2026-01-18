@echo off
echo Running Go Tests...
go test ./tests/go/... -count=1
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Running Python Tests...
.venv\Scripts\activate && python -m pytest tests/python/ -v --tb=short
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo [SUCCESS] All tests passed!
