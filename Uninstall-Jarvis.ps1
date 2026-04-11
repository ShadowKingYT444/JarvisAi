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

function Remove-DirectoryBestEffort([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $true
    }

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
                try {
                    $_.Attributes = "Normal"
                } catch {
                }
            }
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            if ($attempt -lt 3) {
                Start-Sleep -Milliseconds (600 * $attempt)
            }
        }
    }

    return $false
}

function Stop-JarvisProcesses {
    $pidFile = Join-Path $JarvisHome "jarvis.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $pidValue = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pidValue -match "^\d+$") {
            try {
                Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
                Write-Host "  [OK] Stopped running Jarvis process" -ForegroundColor Green
            } catch {
            }
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }

    $portFile = Join-Path $JarvisHome "jarvis.port"
    Remove-Item -LiteralPath $portFile -Force -ErrorAction SilentlyContinue

    try {
        $escapedInstallDir = [Regex]::Escape($InstallDir)
        $pythonProcesses = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue
        foreach ($process in $pythonProcesses) {
            if (-not $process.ExecutablePath) {
                continue
            }
            if ($process.ExecutablePath -notmatch "^$escapedInstallDir(\\|$)") {
                continue
            }
            try {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            } catch {
            }
        }
    } catch {
    }
}

Write-Host ""
Write-Host "== Jarvis AI Uninstaller ==" -ForegroundColor Cyan
Write-Host ""

Stop-JarvisProcesses

$result = & schtasks /delete /tn "JarvisAI" /f 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Removed Task Scheduler entry" -ForegroundColor Green
} else {
    Write-Host "  [--] No Task Scheduler entry found" -ForegroundColor Gray
}

$startupScript = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Jarvis AI.cmd"
if (Test-Path -LiteralPath $startupScript) {
    Remove-Item -LiteralPath $startupScript -Force
    Write-Host "  [OK] Removed Startup-folder script" -ForegroundColor Green
}

if (Test-Path -LiteralPath $InstallDir) {
    $confirm = Read-Host "  Remove install directory ($InstallDir)? (Y/n)"
    if ($confirm -ne "n") {
        if (Remove-DirectoryBestEffort $InstallDir) {
            Write-Host "  [OK] Removed install directory" -ForegroundColor Green
        } else {
            Write-Host "  [!] Could not fully remove install directory because some files are still locked" -ForegroundColor Yellow
        }
    }
}

if (Test-Path -LiteralPath $JarvisHome) {
    Write-Host ""
    Write-Host "  Config directory contains your API keys and conversation history." -ForegroundColor Yellow
    $removeConfig = Read-Host "  Remove config directory ($JarvisHome)? (y/N)"
    if ($removeConfig -eq "y") {
        if (Remove-DirectoryBestEffort $JarvisHome) {
            Write-Host "  [OK] Removed config directory" -ForegroundColor Green
        } else {
            Write-Host "  [!] Could not fully remove config directory because some files are still locked" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [--] Config directory kept" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "  Jarvis AI has been uninstalled." -ForegroundColor Green
Write-Host ""
pause
