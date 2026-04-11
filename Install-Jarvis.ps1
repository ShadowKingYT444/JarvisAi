#Requires -Version 5.1
<#
.SYNOPSIS
    One-click installer for Jarvis AI Desktop Assistant.
.DESCRIPTION
    Checks for Python 3.11+, creates a virtual environment, installs the
    Jarvis package, collects API keys, configures activation methods,
    sets up auto-start via Task Scheduler, and optionally starts the daemon.
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

# ── Banner ────────────────────────────────────────────────────────

Write-Host ""
Write-Host "     ╔══════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "     ║       JARVIS AI v2.0 Installer       ║" -ForegroundColor Blue
Write-Host "     ║   Your Personal Desktop Assistant     ║" -ForegroundColor Blue
Write-Host "     ╚══════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# ── Step 1: Find or install Python ─────────────────────────────────

Write-Header "Step 1/8: Checking Python"

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
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $PythonCmd = "py -3"
            Write-Success "Python installed"
        } catch {
            Write-Fail "Could not install Python via winget."
            Write-Host "  Please install Python 3.11+ from https://python.org/downloads"
            exit 1
        }
    } else {
        Write-Fail "Python 3.11+ is required."
        exit 1
    }
}

# ── Step 2: Create install directory ───────────────────────────────

Write-Header "Step 2/8: Setting up install directory"

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-Success "Install directory: $InstallDir"

# ── Step 3: Create virtual environment ─────────────────────────────

Write-Header "Step 3/8: Creating virtual environment"

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

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip --quiet 2>$null

# ── Step 4: Install Jarvis package ─────────────────────────────────

Write-Header "Step 4/8: Installing Jarvis AI"

Write-Host "  This may take a few minutes (downloading dependencies)..." -ForegroundColor Gray

& $VenvPip install "$ScriptDir" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Package installation failed"
    Write-Host "  Try running manually: $VenvPip install `"$ScriptDir`""
    exit 1
}

Write-Success "Jarvis AI installed"

$JarvisCmd = Join-Path $VenvDir "Scripts\jarvis.exe"
if (Test-Path $JarvisCmd) {
    Write-Success "CLI command: $JarvisCmd"
} else {
    Write-Warn "jarvis CLI not found in venv -- will use python -m jarvis"
    $JarvisCmd = "$VenvPython -m jarvis"
}

# ── Step 5: Collect API keys ──────────────────────────────────────

Write-Header "Step 5/8: API Key Setup"

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

Write-Host "  Jarvis uses Google Gemini as its brain."
Write-Host "  Get a FREE API key at: https://ai.google.dev" -ForegroundColor Yellow
Write-Host ""

$geminiKey = Read-Host "  Gemini API Key (required)"
if (-not $geminiKey) {
    Write-Warn "No Gemini key. Add it later to $envFile"
}

Write-Host ""
Write-Host "  OPTIONAL: Wake word detection ('Hey Jarvis')" -ForegroundColor Gray
Write-Host "  Get a FREE Porcupine key at: https://console.picovoice.ai" -ForegroundColor Yellow
Write-Host "  (Press Enter to skip)" -ForegroundColor Gray
$porcupineKey = Read-Host "  Porcupine Access Key"

Write-Host ""
Write-Host "  OPTIONAL: Premium TTS voice (ElevenLabs)" -ForegroundColor Gray
Write-Host "  (Press Enter to skip for default Windows voice)" -ForegroundColor Gray
$elevenLabsKey = Read-Host "  ElevenLabs API Key"

# Write .env
$envLines = @(
    "# Jarvis API Keys",
    "GOOGLE_API_KEY=$geminiKey"
)
if ($porcupineKey) { $envLines += "PORCUPINE_ACCESS_KEY=$porcupineKey" }
if ($elevenLabsKey) { $envLines += "ELEVENLABS_API_KEY=$elevenLabsKey" }

Set-Content -Path $envFile -Value ($envLines -join "`n")
Write-Success "API keys saved to $envFile"

# ── Step 6: Configure activation methods ─────────────────────────

Write-Header "Step 6/8: Activation Setup"

Write-Host "  How would you like to activate Jarvis?"
Write-Host ""
Write-Host "  1. Double-clap     (clap twice near your mic)" -ForegroundColor White
Write-Host "  2. Wake word       (say 'Jarvis' — requires Porcupine key)" -ForegroundColor White
Write-Host "  3. Hotkey           (Ctrl+Shift+J)" -ForegroundColor White
Write-Host "  4. All of the above" -ForegroundColor White
Write-Host ""

$activationChoice = Read-Host "  Choose activation method(s) [1/2/3/4, default=4]"

$activationMethods = @()
switch ($activationChoice) {
    "1" { $activationMethods = @("clap") }
    "2" { $activationMethods = @("wake_word") }
    "3" { $activationMethods = @("hotkey") }
    default {
        $activationMethods = @("clap", "hotkey")
        if ($porcupineKey) { $activationMethods += "wake_word" }
    }
}

$activationStr = ($activationMethods | ForEach-Object { "  - $_" }) -join "`n"
Write-Success "Activation methods configured"
Write-Host $activationStr -ForegroundColor Gray

# Clap sensitivity
$sensitivity = 0.7
if ($activationMethods -contains "clap") {
    Write-Host ""
    Write-Host "  Clap sensitivity (0.1 = hard to trigger, 1.0 = very sensitive)" -ForegroundColor Gray
    $sensInput = Read-Host "  Sensitivity [default=0.7]"
    if ($sensInput) {
        try { $sensitivity = [float]$sensInput } catch { $sensitivity = 0.7 }
    }
}

# Hotkey
$hotkey = "ctrl+shift+j"
if ($activationMethods -contains "hotkey") {
    Write-Host ""
    $hkInput = Read-Host "  Hotkey combo [default=ctrl+shift+j]"
    if ($hkInput) { $hotkey = $hkInput }
}

# TTS engine
$ttsEngine = "auto"
if ($elevenLabsKey) {
    $ttsEngine = "elevenlabs"
}

# Whisper model size
Write-Host ""
Write-Host "  Speech recognition model size:" -ForegroundColor Gray
Write-Host "    tiny.en  - Fastest, least accurate (< 100 MB)" -ForegroundColor Gray
Write-Host "    base.en  - Good balance (default, ~150 MB)" -ForegroundColor Gray
Write-Host "    small.en - Better accuracy (~500 MB)" -ForegroundColor Gray
$whisperChoice = Read-Host "  Model [default=base.en]"
if (-not $whisperChoice) { $whisperChoice = "base.en" }

# Write config
$activationYaml = "activation_methods:`n" + (($activationMethods | ForEach-Object { "  - $_" }) -join "`n")

$configContent = @"
# Jarvis AI Configuration
gemini_model: gemini-2.0-flash
whisper_model_size: $whisperChoice
tts_engine: $ttsEngine
tts_rate: 180
clap_sensitivity: $sensitivity
hotkey: $hotkey
search_provider: auto
headless: false
$activationYaml
"@

$configFile = Join-Path $JarvisHome "config.yaml"
Set-Content -Path $configFile -Value $configContent
Write-Success "Config saved: $configFile"

# ── Step 7: Set up auto-start ─────────────────────────────────────

Write-Header "Step 7/8: Auto-Start Setup"

$pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = $VenvPython
}

$servicePath = Join-Path $ScriptDir "jarvis\daemon\service.py"

$autoStart = Read-Host "  Start Jarvis automatically on login? (Y/n)"
if ($autoStart -ne "n") {
    $taskCmd = "`"$pythonw`" `"$servicePath`""
    $schtaskOk = $false
    try {
        $ErrorActionPreference = "Continue"
        $null = & schtasks /create /tn "JarvisAI" /tr $taskCmd /sc onlogon /f 2>&1
        if ($LASTEXITCODE -eq 0) { $schtaskOk = $true }
    } catch {}
    $ErrorActionPreference = "Stop"

    if ($schtaskOk) {
        Write-Success "Auto-start enabled (Task Scheduler)"
    } else {
        Write-Warn "Task Scheduler unavailable, using Startup folder"
        $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
        try {
            $ws = New-Object -ComObject WScript.Shell
            $lnk = $ws.CreateShortcut((Join-Path $startupDir "Jarvis AI.lnk"))
            $lnk.TargetPath = $pythonw
            $lnk.Arguments = "`"$servicePath`""
            $lnk.WorkingDirectory = $InstallDir
            $lnk.Description = "Jarvis AI Desktop Assistant"
            $lnk.Save()
            Write-Success "Auto-start enabled (Startup folder)"
        } catch {
            Write-Warn "Could not set up auto-start."
        }
    }
} else {
    Write-Host "  Skipped." -ForegroundColor Gray
}

# ── Step 8: Start Menu shortcut + launch ──────────────────────────

Write-Header "Step 8/8: Finishing Up"

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shortcutPath = Join-Path $startMenuDir "Jarvis AI.lnk"

try {
    $ws = New-Object -ComObject WScript.Shell
    $shortcut = $ws.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$servicePath`""
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "Jarvis AI Desktop Assistant"
    $shortcut.Save()
    Write-Success "Start Menu shortcut created"
} catch {
    Write-Warn "Could not create Start Menu shortcut"
}

# Add jarvis to PATH for this session
$venvScripts = Join-Path $VenvDir "Scripts"
if ($env:Path -notlike "*$venvScripts*") {
    $env:Path = "$venvScripts;$env:Path"
}

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║     Jarvis AI installed and ready!    ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Install location:  $InstallDir" -ForegroundColor Gray
Write-Host "  Config directory:  $JarvisHome" -ForegroundColor Gray
Write-Host "  CLI command:       jarvis" -ForegroundColor Gray
Write-Host ""
Write-Host "  Activation:" -ForegroundColor White
foreach ($m in $activationMethods) {
    switch ($m) {
        "clap"      { Write-Host "    - Double-clap your hands" -ForegroundColor Cyan }
        "wake_word" { Write-Host "    - Say 'Jarvis'" -ForegroundColor Cyan }
        "hotkey"    { Write-Host "    - Press $hotkey" -ForegroundColor Cyan }
    }
}
Write-Host ""

$startNow = Read-Host "  Start Jarvis now? (Y/n)"
if ($startNow -ne "n") {
    Write-Host ""
    Write-Host "  Starting Jarvis..." -ForegroundColor Cyan
    Start-Process -FilePath $VenvPython -ArgumentList "`"$servicePath`"" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Success "Jarvis is running!"
    Write-Host ""
    Write-Host "  Try these commands:" -ForegroundColor White
    Write-Host "    jarvis text `"hello`"       — Send a text command" -ForegroundColor Gray
    Write-Host "    jarvis status              — Check if running" -ForegroundColor Gray
    Write-Host "    jarvis start --verbose     — See all output (debug)" -ForegroundColor Gray
    Write-Host "    jarvis devices             — List audio devices" -ForegroundColor Gray
    Write-Host "    jarvis stop                — Stop Jarvis" -ForegroundColor Gray
} else {
    Write-Host "  To start later:  jarvis start"
}

Write-Host ""
