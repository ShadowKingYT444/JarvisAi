#Requires -Version 5.1
<#
.SYNOPSIS
    Uninstaller for Jarvis AI Desktop Assistant.
.DESCRIPTION
    Removes Task Scheduler entry, Startup-folder script, install directory,
    and optionally the config directory.
#>

$ErrorActionPreference = "SilentlyContinue"
$InstallDir = Join-Path $env:LOCALAPPDATA "JarvisAI"
$JarvisHome = Join-Path $env:USERPROFILE ".jarvis"

Write-Host ""
Write-Host "== Jarvis AI Uninstaller ==" -ForegroundColor Cyan
Write-Host ""

# Stop running daemon
$pidFile = Join-Path $JarvisHome "jarvis.pid"
if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($pid) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "  [OK] Stopped running Jarvis process" -ForegroundColor Green
        } catch {}
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# Remove port file
$portFile = Join-Path $JarvisHome "jarvis.port"
Remove-Item $portFile -Force -ErrorAction SilentlyContinue

# Remove Task Scheduler entry
$result = & schtasks /delete /tn "JarvisAI" /f 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Removed Task Scheduler entry" -ForegroundColor Green
} else {
    Write-Host "  [--] No Task Scheduler entry found" -ForegroundColor Gray
}

# Remove Startup-folder script fallback
$startupScript = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Jarvis AI.cmd"
if (Test-Path $startupScript) {
    Remove-Item $startupScript -Force
    Write-Host "  [OK] Removed Startup-folder script" -ForegroundColor Green
}

# Remove install directory (venv + package)
if (Test-Path $InstallDir) {
    $confirm = Read-Host "  Remove install directory ($InstallDir)? (Y/n)"
    if ($confirm -ne "n") {
        Remove-Item -Recurse -Force $InstallDir
        Write-Host "  [OK] Removed install directory" -ForegroundColor Green
    }
}

# Optionally remove config
if (Test-Path $JarvisHome) {
    Write-Host ""
    Write-Host "  Config directory contains your API keys and conversation history." -ForegroundColor Yellow
    $removeConfig = Read-Host "  Remove config directory ($JarvisHome)? (y/N)"
    if ($removeConfig -eq "y") {
        Remove-Item -Recurse -Force $JarvisHome
        Write-Host "  [OK] Removed config directory" -ForegroundColor Green
    } else {
        Write-Host "  [--] Config directory kept" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "  Jarvis AI has been uninstalled." -ForegroundColor Green
Write-Host ""
pause
