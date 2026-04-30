$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pip    = Join-Path $projectRoot ".venv\Scripts\pip.exe"

# ── 1. Create venv if missing ─────────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# ── 2. Install / upgrade dependencies ─────────────────────────────────────────
Write-Host "Checking dependencies..." -ForegroundColor Yellow
& $pip install -q -r requirements.txt

# ── 3. Start the bot ──────────────────────────────────────────────────────────
Write-Host "Starting bot (press Ctrl+C to stop)..." -ForegroundColor Green
& $python service.py debug
