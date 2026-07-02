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

function Test-AdminShell {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Start-SetuServer {
    if ($restartAsService) {
        Start-Service -Name $ServiceName
        $svc = Get-Service -Name $ServiceName
        $svc.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
        Write-Host "Setu is running as a Windows service." -ForegroundColor Green
    }
    else {
        Start-Process -FilePath $StartScript -ArgumentList @("-Port", "$Port")
        Write-Host "Setu is running in a new window." -ForegroundColor Green
    }
}

function Restore-PreviousVersion {
    Write-Host "Rolling back to the previous version ($previousHead)..." -ForegroundColor Yellow
    & git reset --hard $previousHead | Out-Host
    & $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt") | Out-Host
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

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$restartAsService = $null -ne $service
if ($restartAsService -and -not (Test-AdminShell)) {
    throw "Setu is installed as a Windows service. Right-click update.bat, choose 'Run as administrator', and try again."
}

# Remember the current commit so a failed update can roll back.
$previousHead = (@(& git rev-parse HEAD) -join "").Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($previousHead)) {
    throw "The current commit could not be determined. Run update.bat again."
}

Write-Section "Download Latest Version"
Write-Host "Updating branch '$branch' from origin..."
& git fetch --no-tags origin $branch
if ($LASTEXITCODE -ne 0) {
    throw "Git could not download the latest version. Your existing files were left intact; check the Git message above and run update.bat again."
}

# Normally the update is a clean fast-forward, so try that first. This keeps the
# updater independent of machine-wide pull.rebase settings and never rebases.
# This deployment machine never commits to the project, so if history has
# diverged (e.g. the remote branch was force-pushed / rewritten) a fast-forward
# is impossible -- fall back to matching the remote exactly with a hard reset.
# Data files (data/setu.db, .env, data/secret_key) are gitignored, so the reset
# only rewinds tracked source files and never touches live data or config.
& git merge --ff-only FETCH_HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Host "A clean fast-forward was not possible (the remote history was rewritten)." -ForegroundColor Yellow
    Write-Host "Resetting local files to match origin/$branch exactly (your data and .env are untouched)..." -ForegroundColor Yellow
    & git reset --hard FETCH_HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "Git could not sync the project to the latest version. Your data files were left intact; check the Git message above and run update.bat again."
    }
}

if (-not (Test-Path $StopScript)) {
    throw "The server management helper is missing after the update: '$StopScript'."
}

Write-Section "Stop Existing Server"
& $StopScript -ProjectDir $ProjectRoot -ServiceName $ServiceName

# Stop before pip: Windows can't replace .pyd/.dll files a running server holds.
# On failure the server is already down, so roll back and restart it.
try {
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
}
catch {
    Write-Section "Recover After Failed Update"
    Write-Host "The update failed after the server was stopped: $($_.Exception.Message)" -ForegroundColor Red
    try {
        Restore-PreviousVersion
    }
    catch {
        Write-Host "Automatic rollback failed. Resolve the Git/pip message above before retrying." -ForegroundColor Red
    }
    try {
        Start-SetuServer
        Write-Host "The previous version was restored and the server is running again." -ForegroundColor Yellow
    }
    catch {
        Write-Host "The server could not be restarted automatically. Start it manually with start_setu.bat." -ForegroundColor Red
    }
    throw
}

Write-Section "Restart Server"
Start-SetuServer
Write-Host "Setu was updated successfully." -ForegroundColor Green
Write-Host "Local URL: http://127.0.0.1:$Port"
