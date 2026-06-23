param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Setu is not set up yet. Run setup.bat or setup.ps1 first." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

Set-Location $ProjectRoot
Write-Host "Starting Setu QR Tally Bridge..."
Write-Host "Open: http://127.0.0.1:$Port"
Write-Host "Press Ctrl+C in this window to stop the app."
& $VenvPython -m uvicorn app.main:app --host $HostAddress --port $Port
