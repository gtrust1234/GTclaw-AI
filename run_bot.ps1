$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at .venv — run: python -m venv .venv"
    exit 1
}

Write-Host "Starting bot..." -ForegroundColor Cyan
& $python "service.py" "debug"