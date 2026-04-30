#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install, start, stop, or remove the Personal AI Assistant Windows service.
    Must be run as Administrator.

.EXAMPLE
    .\service_install.ps1 install   # register + start service
    .\service_install.ps1 start
    .\service_install.ps1 stop
    .\service_install.ps1 restart
    .\service_install.ps1 remove    # stop + unregister
    .\service_install.ps1 status
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("install","start","stop","restart","remove","status","debug")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$servicePy = Join-Path $root "service.py"

# Check python exists
if (-not (Test-Path $python)) {
    Write-Error "Virtual environment not found at $venv. Run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
}

function Invoke-ServiceCmd($args_) {
    & $python $servicePy @args_
}

switch ($Action) {
    "install" {
        Write-Host "Installing Windows service..." -ForegroundColor Cyan
        Invoke-ServiceCmd "install"
        Write-Host "Starting service..." -ForegroundColor Cyan
        Invoke-ServiceCmd "start"
        Write-Host "Service installed and started." -ForegroundColor Green
    }
    "start" {
        Write-Host "Starting service..." -ForegroundColor Cyan
        Invoke-ServiceCmd "start"
    }
    "stop" {
        Write-Host "Stopping service..." -ForegroundColor Yellow
        Invoke-ServiceCmd "stop"
    }
    "restart" {
        Write-Host "Restarting service..." -ForegroundColor Yellow
        Invoke-ServiceCmd "stop"
        Start-Sleep -Seconds 2
        Invoke-ServiceCmd "start"
        Write-Host "Service restarted." -ForegroundColor Green
    }
    "remove" {
        Write-Host "Stopping and removing service..." -ForegroundColor Red
        try { Invoke-ServiceCmd "stop" } catch {}
        Invoke-ServiceCmd "remove"
        Write-Host "Service removed." -ForegroundColor Green
    }
    "status" {
        $svc = Get-Service -Name "PersonalAIAssistant" -ErrorAction SilentlyContinue
        if ($svc) {
            Write-Host "Service status: $($svc.Status)" -ForegroundColor $(if ($svc.Status -eq 'Running') {'Green'} else {'Yellow'})
        } else {
            Write-Host "Service is NOT installed." -ForegroundColor Red
        }
    }
    "debug" {
        Write-Host "Running bot directly (no service manager)..." -ForegroundColor Cyan
        Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
        & $python $servicePy debug
    }
}
