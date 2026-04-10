@echo off
echo ============================================
echo   Jarvis AI Installer
echo ============================================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0Install-Jarvis.ps1"
if %ERRORLEVEL% neq 0 (
    echo.
    echo Installation encountered an error. Check the output above.
)
echo.
pause
