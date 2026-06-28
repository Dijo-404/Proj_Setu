@echo off
setlocal
cd /d "%~dp0"
set "SETU_UPDATE_BAT=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $path=$env:SETU_UPDATE_BAT; $marker='### POWERSHELL UPDATE SCRIPT ###'; $raw=Get-Content -Raw -LiteralPath $path; $start=$raw.LastIndexOf($marker); if ($start -lt 0) { throw 'Embedded update script marker not found.' }; $code=$raw.Substring($start + $marker.Length); & ([scriptblock]::Create($code)) @args" %*
set "UPDATE_EXIT=%ERRORLEVEL%"
echo.
if not "%UPDATE_EXIT%"=="0" echo Update did not complete successfully. The error above explains what needs attention.
pause
exit /b %UPDATE_EXIT%

### POWERSHELL UPDATE SCRIPT ###
param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $env:SETU_UPDATE_BAT
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$StartScript = Join-Path $ProjectRoot "start_setu.bat"
$StopScript = Join-Path $ProjectRoot "deployment\windows\stop_setu.ps1"
$ServiceName = "SetuQrTallyBridge"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

Set-Location $ProjectRoot

if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    throw "Git was not found. Install Git for Windows, then run update.bat again."
}
if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
    throw "'$ProjectRoot' is not a Git checkout. Clone https://github.com/Dijo-404/Proj_Setu.git before using update.bat."
}
if (-not (Test-Path $VenvPython)) {
    throw "Setu is not set up yet. Run setup.bat first."
}

$branch = (@(& git branch --show-current) -join "").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    throw "The current Git branch could not be determined. Check out the branch you want to update and try again."
}

$originUrl = (@(& git remote get-url origin) -join "").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($originUrl)) {
    throw "The Git remote named 'origin' is missing. It should point to https://github.com/Dijo-404/Proj_Setu.git."
}
if ($originUrl -notmatch "(?i)github\.com[:/]Dijo-404/Proj_Setu(?:\.git)?/?$") {
    throw "The Git remote named 'origin' points to '$originUrl', not https://github.com/Dijo-404/Proj_Setu.git."
}

Write-Section "Download Latest Version"
Write-Host "Updating branch '$branch' from origin..."
& git pull --ff-only origin $branch
if ($LASTEXITCODE -ne 0) {
    throw "Git could not fast-forward the project. Your existing files were left intact; resolve the Git message above and run update.bat again."
}

if (-not (Test-Path $StopScript)) {
    throw "The server management helper is missing after the update: '$StopScript'."
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$restartAsService = $null -ne $service

Write-Section "Stop Existing Server"
& $StopScript -ProjectDir $ProjectRoot -ServiceName $ServiceName

Write-Section "Update Dependencies"
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

Write-Section "Smoke Test"
& $VenvPython -c "from app.main import app; print('App import OK')"
if ($LASTEXITCODE -ne 0) {
    throw "The updated app could not be imported. Check the error above."
}

Write-Section "Restart Server"
if ($restartAsService) {
    Start-Service -Name $ServiceName
    $service = Get-Service -Name $ServiceName
    $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
    Write-Host "Setu was updated and restarted as a Windows service." -ForegroundColor Green
}
else {
    Start-Process -FilePath $StartScript -ArgumentList @("-Port", "$Port")
    Write-Host "Setu was updated and restarted in a new window." -ForegroundColor Green
}
Write-Host "Local URL: http://127.0.0.1:$Port"
