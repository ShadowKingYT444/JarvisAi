@echo off
setlocal
echo ============================================
echo   Jarvis AI Installer
echo ============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Jarvis.ps1"
if errorlevel 1 (
    echo.
    echo Installation encountered an error. Check the output above.
)
echo.
pause
