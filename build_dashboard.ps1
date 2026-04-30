# build_dashboard.ps1 — Builds GTclaw Dashboard into a standalone EXE
# Run: .\build_dashboard.ps1

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"

Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
& $python -m pip install -q pyinstaller

Write-Host "Building EXE..." -ForegroundColor Cyan
& $python -m PyInstaller `
    --onefile `
    --windowed `
    --name "GTclawDashboard" `
    --add-data "config;config" `
    --hidden-import "PyQt5.sip" `
    --hidden-import "apscheduler" `
    dashboard.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Build complete!" -ForegroundColor Green
    Write-Host "EXE is at: dist\GTclawDashboard.exe" -ForegroundColor Green
    Write-Host ""
    Write-Host "NOTE: The EXE must be run from the project folder (or" -ForegroundColor Yellow
    Write-Host "      have the config/ folder next to it) to find the database." -ForegroundColor Yellow
} else {
    Write-Host "Build failed." -ForegroundColor Red
}
