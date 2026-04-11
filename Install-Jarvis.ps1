#Requires -Version 5.1
<#
.SYNOPSIS
    Windows bootstrapper for Jarvis AI Desktop Assistant.
.DESCRIPTION
    Verifies Python 3.11+, creates a local virtual environment, installs the
    Jarvis package, then launches the Python setup wizard.
#>

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$InstallDir = Join-Path $env:LOCALAPPDATA 'JarvisAI'
$VenvDir = Join-Path $InstallDir 'venv'

function Write-Header($text) {
    Write-Host ''
    Write-Host ('== ' + $text + ' ==') -ForegroundColor Cyan
    Write-Host ''
}

function Write-Ok($text) {
    Write-Host ('  [OK] ' + $text) -ForegroundColor Green
}

function Write-Warn($text) {
    Write-Host ('  [!] ' + $text) -ForegroundColor Yellow
}

function Write-Fail($text) {
    Write-Host ('  [X] ' + $text) -ForegroundColor Red
}

function Get-PythonLauncher {
    $candidates = @(
        @{ Command = 'py'; Args = @('-3') },
        @{ Command = 'python'; Args = @() },
        @{ Command = 'python3'; Args = @() }
    )

    foreach ($candidate in $candidates) {
        try {
            $versionOutput = & $($candidate.Command) @($candidate.Args) --version 2>&1
            if ($versionOutput -match 'Python (\d+)\.(\d+)') {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 11) {
                    return [pscustomobject]@{
                        Command = $candidate.Command
                        Args    = $candidate.Args
                        Version = $versionOutput
                    }
                }
            }
        } catch {
        }
    }

    return $null
}

Write-Host ''
Write-Host '     ╔══════════════════════════════════════╗' -ForegroundColor Blue
Write-Host '     ║       JARVIS AI v2.0 Installer       ║' -ForegroundColor Blue
Write-Host '     ║        Windows bootstrap flow        ║' -ForegroundColor Blue
Write-Host '     ╚══════════════════════════════════════╝' -ForegroundColor Blue
Write-Host ''

Write-Header 'Step 1/4: Checking Python'
$PythonLauncher = Get-PythonLauncher

if (-not $PythonLauncher) {
    Write-Warn 'Python 3.11+ not found.'
    $installPython = Read-Host 'Install Python 3.12 via winget? (Y/n)'
    if ($installPython -ne 'n') {
        try {
            Write-Host 'Installing Python 3.12...' -ForegroundColor Cyan
            & winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
            $PythonLauncher = [pscustomobject]@{
                Command = 'py'
                Args    = @('-3')
                Version = 'Python 3.12'
            }
            Write-Ok 'Python installed'
        } catch {
            Write-Fail 'Could not install Python automatically.'
            Write-Host 'Install Python 3.11+ from https://python.org/downloads'
            exit 1
        }
    } else {
        Write-Fail 'Python 3.11+ is required.'
        exit 1
    }
}

Write-Ok ('Found ' + $PythonLauncher.Version)

Write-Header 'Step 2/4: Creating environment'
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

if (Test-Path $VenvDir) {
    Write-Warn 'Existing venv found - reinstalling'
    Remove-Item -Recurse -Force $VenvDir
}

& $($PythonLauncher.Command) @($PythonLauncher.Args) -m venv $VenvDir

$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    Write-Fail 'Failed to create the virtual environment.'
    exit 1
}

Write-Ok ('Virtual environment created at ' + $VenvDir)
& $VenvPython -m pip install --upgrade pip --quiet 2>$null

Write-Header 'Step 3/4: Installing Jarvis'
Write-Host 'Installing the package and dependencies. This can take a few minutes...' -ForegroundColor Gray

& $VenvPython -m pip install $ScriptDir --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'Package installation failed.'
    Write-Host ('Run this manually if needed: {0} -m pip install {1}' -f $VenvPython, $ScriptDir)
    exit 1
}

Write-Ok 'Jarvis installed'

Write-Header 'Step 4/4: Launching setup wizard'
Write-Host 'The wizard will collect your API keys, microphone choice, and startup profile.' -ForegroundColor Gray
Write-Host 'Recommended launch profile: double-clap to initialize, then wake word Jarvis.' -ForegroundColor Gray

& $VenvPython -m jarvis install
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'Setup wizard failed.'
    exit $LASTEXITCODE
}

Write-Host ''
Write-Ok 'Jarvis setup completed'
Write-Host 'Use jarvis start later to launch manually.' -ForegroundColor Gray
Write-Host ''
