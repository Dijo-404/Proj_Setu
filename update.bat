@echo off
setlocal
cd /d "%~dp0"
set "SETUORA_NO_PAUSE=0"
if /I "%~1"=="--no-pause" (
    set "SETUORA_NO_PAUSE=1"
    shift
)
set "SETUORA_UPDATE_BAT=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $path=$env:SETUORA_UPDATE_BAT; $marker='### POWERSHELL UPDATE SCRIPT ###'; $raw=Get-Content -Raw -LiteralPath $path; $start=$raw.LastIndexOf($marker); if ($start -lt 0) { throw 'Embedded update script marker not found.' }; $code=$raw.Substring($start + $marker.Length); & ([scriptblock]::Create($code)) @args" %*
set "UPDATE_EXIT=%ERRORLEVEL%"
echo.
if not "%UPDATE_EXIT%"=="0" echo Update did not complete successfully. The error above explains what needs attention.
if not "%SETUORA_NO_PAUSE%"=="1" pause
exit /b %UPDATE_EXIT%

### POWERSHELL UPDATE SCRIPT ###
param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $env:SETUORA_UPDATE_BAT
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RequirementsLock = Join-Path $ProjectRoot "requirements.lock"
$StartScript = Join-Path $ProjectRoot "start_setuora.bat"
$StopScript = Join-Path $ProjectRoot "deployment\windows\stop_setuora.ps1"
$ProcessHelper = Join-Path $ProjectRoot "deployment\windows\server_processes.ps1"
$ServiceName = "SetuoraQrTallyBridge"
$CaddyServiceName = "SetuoraCaddy"
$restartAsService = $false
$restartAsConsole = $false
$restartHostAddress = "127.0.0.1"
$restartPort = $Port
$updateStarted = $false

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

function Ensure-Pip {
    & $VenvPython -m pip --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "pip is missing from the virtual environment. Repairing pip with ensurepip..."
    & $VenvPython -m ensurepip --upgrade | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "pip is missing and could not be repaired. Reinstall Python 3.11 with pip enabled, then run setup.bat again."
    }

    & $VenvPython -m pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pip is still unavailable after repair. Delete .venv, reinstall Python 3.11 with pip enabled, and run setup.bat again."
    }
}

function Start-SetuoraServer {
    if ($restartAsService) {
        $caddyService = Get-Service -Name $CaddyServiceName -ErrorAction SilentlyContinue
        if ($caddyService -and $caddyService.Status -ne "Running") {
            Start-Service -Name $CaddyServiceName
            $caddyService.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
        }
        Start-Service -Name $ServiceName
        $svc = Get-Service -Name $ServiceName
        $svc.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
        Write-Host "Setuora is running as a Windows service." -ForegroundColor Green
        return $true
    }

    if ($restartAsConsole) {
        Start-Process -FilePath $StartScript -ArgumentList @("-HostAddress", "$restartHostAddress", "-Port", "$restartPort")
        Write-Host "Setuora is running in a new window." -ForegroundColor Green
        return $true
    }

    Write-Host "Setuora was not running before the update; leaving it stopped." -ForegroundColor Yellow
    return $false
}

function Restore-PreviousVersion {
    if (-not $updateStarted) {
        return
    }
    Write-Host "Rolling back to the previous version ($previousHead)..." -ForegroundColor Yellow
    # This is safe because update.bat requires a clean worktree before changing
    # source files, and this reset only returns the updater's own fast-forward.
    & git reset --hard $previousHead | Out-Host
    Ensure-Pip
    & $VenvPython -m pip install --require-hashes -r $RequirementsLock | Out-Host
}

Set-Location $ProjectRoot

if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    throw "Git was not found. Install Git for Windows, then run update.bat again."
}
if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
    throw "'$ProjectRoot' is not a Git checkout. Clone https://github.com/Dijo-404/Proj_Setu.git before using update.bat."
}
if (-not (Test-Path $VenvPython)) {
    throw "Setuora is not set up yet. Run setup.bat first."
}
if (-not (Test-Path $RequirementsLock)) {
    throw "The pinned dependency lockfile is missing: '$RequirementsLock'. Reinstall from a complete release."
}
if (-not (Test-Path $ProcessHelper)) {
    throw "The Setuora process helper is missing: '$ProcessHelper'."
}
. $ProcessHelper

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
$restartAsService = $service -and $service.Status -ne "Stopped"
$runningSetuoraProcesses = @(Get-SetuoraServerProcesses -ProjectRoot $ProjectRoot -ExcludeProcessIds @($PID))
$restartAsConsole = (-not $restartAsService) -and $runningSetuoraProcesses.Count -gt 0
if ($restartAsConsole) {
    $launchInfo = Get-SetuoraServerLaunchInfo -Process $runningSetuoraProcesses[0] -DefaultHostAddress $restartHostAddress -DefaultPort $restartPort
    $restartHostAddress = $launchInfo.HostAddress
    $restartPort = $launchInfo.Port
}
if ($restartAsService -and -not (Test-AdminShell)) {
    throw "Setuora is installed as a Windows service. Right-click update.bat, choose 'Run as administrator', and try again."
}

$worktreeChanges = @(& git status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw "Git could not inspect the working tree. Your installation was left unchanged."
}
if ($worktreeChanges.Count -gt 0) {
    throw "Refusing to update because local source changes are present. Commit or stash them first; update.bat never overwrites local code."
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

# Only accept a clean fast-forward. A rewritten or divergent remote must be
# reviewed manually; the updater never resets an installation to another commit.
& git merge --ff-only FETCH_HEAD
if ($LASTEXITCODE -ne 0) {
    throw "A clean fast-forward was not possible. No files were replaced; review the remote history before updating."
}
$updateStarted = $true

if (-not (Test-Path $StopScript)) {
    throw "The server management helper is missing after the update: '$StopScript'."
}

Write-Section "Stop Existing Server"
& $StopScript -ProjectDir $ProjectRoot -ServiceName $ServiceName

# Stop before pip: Windows can't replace .pyd/.dll files a running server holds.
# On failure the server is already down, so roll back and restart it.
try {
    Write-Section "Update Dependencies"
    Ensure-Pip
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upgrade pip."
    }

    & $VenvPython -m pip install --require-hashes -r $RequirementsLock
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed."
    }
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "Installed Python dependencies are inconsistent. Check the pip message above."
    }

    Write-Section "Smoke Test"
    & $VenvPython -c "import uvicorn; from app.main import app; print('App import OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "The updated app could not be imported. Check the error above."
    }

    Write-Section "Regression Tests"
    & $VenvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "The updated release did not pass its test suite."
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
        $serverRestarted = Start-SetuoraServer
        if ($serverRestarted) {
            Write-Host "The previous version was restored and the server is running again." -ForegroundColor Yellow
        }
        else {
            Write-Host "The previous version was restored. Setuora was left stopped because it was not running before the update." -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "The server could not be restarted automatically. Start it manually with start_setuora.bat." -ForegroundColor Red
    }
    throw
}

Write-Section "Restart Server"
$serverRestarted = Start-SetuoraServer
Write-Host "Setuora was updated successfully." -ForegroundColor Green
if ($serverRestarted) {
    if ($restartAsService) {
        Write-Host "Local URL: http://127.0.0.1:$Port"
    }
    else {
        Write-Host "Local URL: http://${restartHostAddress}:$restartPort"
    }
}
