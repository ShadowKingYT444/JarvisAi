#Requires -Version 5.1
<#
.SYNOPSIS
    One-click installer for Jarvis AI Desktop Assistant.
.DESCRIPTION
    Checks for Python 3.11+, creates a virtual environment, installs the
    Jarvis package, collects API keys, sets up auto-start via Task Scheduler,
    and optionally starts the daemon immediately.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$InstallDir = Join-Path $env:LOCALAPPDATA "JarvisAI"
$JarvisHome = Join-Path $env:USERPROFILE ".jarvis"
$VenvDir = Join-Path $InstallDir "venv"

function Write-Header($text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success($text) {
    Write-Host "  [OK] $text" -ForegroundColor Green
}

function Write-Warn($text) {
    Write-Host "  [!] $text" -ForegroundColor Yellow
}

function Write-Fail($text) {
    Write-Host "  [X] $text" -ForegroundColor Red
}

# ── Step 1: Find or install Python ─────────────────────────────────

Write-Header "Checking Python"

$PythonCmd = $null

# Try py launcher first (most reliable on Windows)
try {
    $pyVersion = & py -3 --version 2>&1
    if ($pyVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 11) {
            $PythonCmd = "py -3"
            Write-Success "Found $pyVersion (via py launcher)"
        }
    }
} catch {}

# Try python directly
if (-not $PythonCmd) {
    try {
        $pyVersion = & python --version 2>&1
        if ($pyVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $PythonCmd = "python"
                Write-Success "Found $pyVersion"
            }
        }
    } catch {}
}

# Try python3
if (-not $PythonCmd) {
    try {
        $pyVersion = & python3 --version 2>&1
        if ($pyVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $PythonCmd = "python3"
                Write-Success "Found $pyVersion"
            }
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Warn "Python 3.11+ not found."
    Write-Host ""
    $install = Read-Host "  Install Python 3.12 via winget? (Y/n)"
    if ($install -ne "n") {
        try {
            Write-Host "  Installing Python 3.12..." -ForegroundColor Cyan
            & winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $PythonCmd = "py -3"
            Write-Success "Python installed"
        } catch {
            Write-Fail "Could not install Python via winget."
            Write-Host "  Please install Python 3.11+ from https://python.org/downloads"
            Write-Host "  Then re-run this installer."
            exit 1
        }
    } else {
        Write-Fail "Python 3.11+ is required."
        Write-Host "  Download from: https://python.org/downloads"
        exit 1
    }
}

# ── Step 2: Create install directory ───────────────────────────────

Write-Header "Setting up install directory"

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Success "Install directory: $InstallDir"

# ── Step 3: Create virtual environment ─────────────────────────────

Write-Header "Creating virtual environment"

if (Test-Path $VenvDir) {
    Write-Warn "Existing venv found -- reinstalling"
    Remove-Item -Recurse -Force $VenvDir
}

if ($PythonCmd -eq "py -3") {
    & py -3 -m venv $VenvDir
} else {
    & $PythonCmd -m venv $VenvDir
}

if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Fail "Failed to create virtual environment"
    exit 1
}

Write-Success "Virtual environment created"

# Activate venv for remaining commands
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

# Upgrade pip
& $VenvPython -m pip install --upgrade pip --quiet 2>$null

# ── Step 4: Install Jarvis package ─────────────────────────────────

Write-Header "Installing Jarvis AI"

Write-Host "  This may take a few minutes (downloading dependencies)..." -ForegroundColor Gray

& $VenvPip install "$ScriptDir" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Package installation failed"
    Write-Host "  Try running manually: $VenvPip install `"$ScriptDir`""
    exit 1
}

Write-Success "Jarvis AI installed"

# Verify the jarvis command exists
$JarvisCmd = Join-Path $VenvDir "Scripts\jarvis.exe"
if (Test-Path $JarvisCmd) {
    Write-Success "CLI command available: $JarvisCmd"
} else {
    Write-Warn "jarvis CLI not found in venv -- will use python -m jarvis"
    $JarvisCmd = "$VenvPython -m jarvis"
}

# ── Step 5: Collect API keys ──────────────────────────────────────

Write-Header "API Key Setup"

# Create .jarvis directory
if (-not (Test-Path $JarvisHome)) {
    New-Item -ItemType Directory -Path $JarvisHome -Force | Out-Null
}
foreach ($sub in @("logs", "conversations", "backups")) {
    $subPath = Join-Path $JarvisHome $sub
    if (-not (Test-Path $subPath)) {
        New-Item -ItemType Directory -Path $subPath -Force | Out-Null
    }
}

$envFile = Join-Path $JarvisHome ".env"

Write-Host "  Jarvis requires a Google Gemini API key to function."
Write-Host "  Get one free at: https://ai.google.dev" -ForegroundColor Gray
Write-Host ""

$geminiKey = Read-Host "  Gemini API Key (required)"
if (-not $geminiKey) {
    Write-Warn "No Gemini key provided. You can add it later in $envFile"
}

Write-Host ""
Write-Host "  Optional: Search API key enables web search functionality."
Write-Host "  Get one at: https://console.cloud.google.com" -ForegroundColor Gray
Write-Host ""

$searchKey = Read-Host "  Search API Key (optional, press Enter to skip)"
$searchEngineId = ""
if ($searchKey) {
    $searchEngineId = Read-Host "  Google CSE Search Engine ID"
}

# Write .env file
$envContent = @"
# Jarvis API Keys
GOOGLE_API_KEY=$geminiKey
SEARCH_API_KEY=$searchKey
SEARCH_ENGINE_ID=$searchEngineId
# ELEVENLABS_API_KEY=
"@
Set-Content -Path $envFile -Value $envContent
Write-Success "API keys saved to $envFile"

# ── Step 6: Create config ─────────────────────────────────────────

$configFile = Join-Path $JarvisHome "config.yaml"
if (-not (Test-Path $configFile)) {
    $configContent = @"
# Jarvis AI Configuration
gemini_model: gemini-2.0-flash
whisper_model_size: base.en
tts_engine: pyttsx3
tts_voice: ""
tts_rate: 180
clap_sensitivity: 0.7
search_provider: google_cse
headless: false
"@
    Set-Content -Path $configFile -Value $configContent
    Write-Success "Config created: $configFile"
} else {
    Write-Success "Config already exists: $configFile"
}

# ── Step 7: Set up auto-start ─────────────────────────────────────

Write-Header "Auto-Start Setup"

$pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = $VenvPython
}

$servicePath = Join-Path $ScriptDir "jarvis\daemon\service.py"

$autoStart = Read-Host "  Start Jarvis automatically on login? (Y/n)"
if ($autoStart -ne "n") {
    $taskCmd = "`"$pythonw`" `"$servicePath`" --headless"
    $result = & schtasks /create /tn "JarvisAI" /tr $taskCmd /sc onlogon /rl highest /f 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Task Scheduler entry created (runs on login)"
    } else {
        Write-Warn "Could not create scheduled task (may need admin rights)"
        Write-Host "  You can run Jarvis manually: $JarvisCmd start --headless"
    }
} else {
    Write-Host "  Skipped. Run manually: $JarvisCmd start --headless" -ForegroundColor Gray
}

# ── Step 8: Create Start Menu shortcut ────────────────────────────

Write-Header "Creating Shortcuts"

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $startMenuDir "Jarvis AI.lnk"

try {
    $ws = New-Object -ComObject WScript.Shell
    $shortcut = $ws.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$servicePath`" --headless"
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "Jarvis AI Desktop Assistant"
    $shortcut.Save()
    Write-Success "Start Menu shortcut created"
} catch {
    Write-Warn "Could not create Start Menu shortcut"
}

# ── Step 9: Offer to start now ────────────────────────────────────

Write-Header "Setup Complete!"

Write-Host "  Jarvis AI has been installed successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Install location:  $InstallDir"
Write-Host "  Config directory:  $JarvisHome"
Write-Host "  CLI command:       $JarvisCmd"
Write-Host ""

$startNow = Read-Host "  Start Jarvis now? (Y/n)"
if ($startNow -ne "n") {
    Write-Host "  Starting Jarvis in background..." -ForegroundColor Cyan
    Start-Process -FilePath $pythonw -ArgumentList "`"$servicePath`" --headless" -WindowStyle Hidden
    Write-Success "Jarvis is running in the background!"
    Write-Host ""
    Write-Host "  Send a command:  $JarvisCmd text `"hello`""
    Write-Host "  Check status:    $JarvisCmd status"
    Write-Host "  View logs:       $JarvisCmd log"
    Write-Host "  Stop:            $JarvisCmd stop"
} else {
    Write-Host "  To start later:  $JarvisCmd start --headless"
}

Write-Host ""
