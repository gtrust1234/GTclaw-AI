#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build script — creates standalone EXE files and (optionally) the Inno Setup installer.

.DESCRIPTION
    Requires:
      - Python + venv with all dependencies installed
      - PyInstaller  (pip install pyinstaller)
      - Inno Setup 6 (optional, for installer — default path checked automatically)

.EXAMPLE
    .\build.ps1              # build EXEs only
    .\build.ps1 -Installer   # build EXEs + run Inno Setup
    .\build.ps1 -Clean       # remove previous build artefacts first
#>

param(
    [switch]$Installer,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$pip = Join-Path $venv "Scripts\pip.exe"
$pyinstaller = Join-Path $venv "Scripts\pyinstaller.exe"

Write-Host "=== Personal AI Assistant Build ===" -ForegroundColor Cyan

# ── Clean ─────────────────────────────────────────────────────────────────────
if ($Clean) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\build", "$root\dist", "$root\installer_output"
}

# ── Ensure venv ───────────────────────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $venv
}

Write-Host "Installing / updating dependencies..." -ForegroundColor Yellow
& $pip install -q --upgrade pip
& $pip install -q -r (Join-Path $root "requirements.txt")
& $pip install -q pyinstaller

# ── Build dashboard EXE ───────────────────────────────────────────────────────
Write-Host "Building GTclawDashboard.exe..." -ForegroundColor Cyan
& $pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "GTclawDashboard" `
    --icon "$root\logo.ico" `
    --add-data "$root\logo.ico;." `
    --paths "$root" `
    --hidden-import "dashboard.tabs.code_editor" `
    --hidden-import "dashboard.tabs.identity" `
    --hidden-import "identity_manager" `
    --hidden-import "config_manager" `
    --hidden-import "terminal_executor" `
    --hidden-import "anthropic" `
    --distpath "$root\dist" `
    --workpath "$root\build\dashboard" `
    (Join-Path $root "dashboard.py")

if ($LASTEXITCODE -ne 0) { Write-Error "Dashboard PyInstaller failed (exit $LASTEXITCODE). Is GTclawDashboard.exe still running?"; exit 1 }
if (-not (Test-Path "$root\dist\GTclawDashboard.exe")) { Write-Error "Dashboard build failed (EXE not found)"; exit 1 }

# ── Build service EXE ─────────────────────────────────────────────────────────
Write-Host "Building GTclawService.exe..." -ForegroundColor Cyan
& $pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "GTclawService" `
    --icon "$root\logo.ico" `
    --distpath "$root\dist" `
    --workpath "$root\build\service" `
    --paths "$root" `
    --hidden-import "bot" `
    --hidden-import "briefing" `
    --hidden-import "memory" `
    --hidden-import "database" `
    --hidden-import "config_manager" `
    --hidden-import "claude_client" `
    --hidden-import "terminal_executor" `
    --hidden-import "email_scanner" `
    --hidden-import "identity_manager" `
    --hidden-import "proactive_agent" `
    (Join-Path $root "service.py")

if (-not (Test-Path "$root\dist\GTclawService.exe")) { Write-Error "Service build failed (EXE not found)"; exit 1 }

Write-Host "EXE build complete:" -ForegroundColor Green
Write-Host "  Dashboard: $root\dist\GTclawDashboard.exe"
Write-Host "  Service:   $root\dist\GTclawService.exe"

# ── Inno Setup installer ──────────────────────────────────────────────────────
if ($Installer) {
    $iscc_paths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $iscc_paths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $iscc) {
        Write-Warning "Inno Setup 6 not found -- skipping installer build."
        Write-Warning "Download from: https://jrsoftware.org/isinfo.php"
        Write-Warning "Then re-run:   .\build.ps1 -Installer"
    } else {
        Write-Host "Building installer with Inno Setup..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force -Path "$root\installer_output" | Out-Null
        & $iscc (Join-Path $root "installer.iss")
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Installer ready: $root\installer_output\GTclawAI_Setup_*.exe" -ForegroundColor Green
        } else {
            Write-Error "Inno Setup compilation failed (exit $LASTEXITCODE)"
        }
    }
}

Write-Host "=== Build finished ===" -ForegroundColor Green
