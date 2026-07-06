param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [string]$ServiceName = "SetuQrTallyBridge"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath($ProjectDir).TrimEnd("\")
$pythonExe = [IO.Path]::GetFullPath((Join-Path $projectRoot ".venv\Scripts\python.exe"))
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$processHelper = Join-Path $PSScriptRoot "server_processes.ps1"
Set-Location $projectRoot

function Ensure-Pip {
    param([string]$PythonExe)

    & $PythonExe -m pip --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "pip is missing from the virtual environment. Repairing pip with ensurepip..."
    & $PythonExe -m ensurepip --upgrade | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "pip is missing and could not be repaired. Run setup.bat again after reinstalling Python 3.11 with pip enabled."
    }

    & $PythonExe -m pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pip is still unavailable after repair. Delete .venv, reinstall Python 3.11 with pip enabled, and run setup.bat again."
    }
}

function Test-AppDependencies {
    param(
        [string]$PythonExe,
        [switch]$Quiet
    )

    if ($Quiet) {
        & $PythonExe -c "import uvicorn; from app.main import app" | Out-Null
    }
    else {
        & $PythonExe -c "import uvicorn; from app.main import app"
    }
    return ($LASTEXITCODE -eq 0)
}

function Ensure-AppDependencies {
    param(
        [string]$PythonExe,
        [string]$RequirementsPath
    )

    if (Test-AppDependencies -PythonExe $PythonExe -Quiet) {
        return
    }

    if (-not (Test-Path -LiteralPath $RequirementsPath)) {
        throw "Python packages are missing and requirements.txt was not found at '$RequirementsPath'. Run setup.bat again from the project folder."
    }

    Write-Host "Python packages are missing or incomplete. Installing requirements..."
    Ensure-Pip -PythonExe $PythonExe

    & $PythonExe -m pip install --upgrade pip | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upgrade pip."
    }

    & $PythonExe -m pip install -r $RequirementsPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed. Check the pip message above, then run setup.bat again."
    }

    & $PythonExe -m pip check | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Installed Python dependencies are inconsistent. Check the pip message above."
    }

    if (-not (Test-AppDependencies -PythonExe $PythonExe)) {
        throw "The app still could not be imported after installing requirements. Check the Python error above."
    }
}

if (-not (Test-Path -LiteralPath $processHelper)) {
    throw "The Setu process helper was not found: '$processHelper'."
}
. $processHelper

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Setu is not set up yet. Run setup.bat first."
}

Ensure-AppDependencies -PythonExe $pythonExe -RequirementsPath $requirementsPath

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -eq "Running") {
        Write-Host "Setu is already running as the Windows service."
    }
    else {
        Write-Host "Starting the Setu Windows service..."
        try {
            Start-Service -Name $ServiceName
            $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
            Write-Host "Setu is running as the Windows service." -ForegroundColor Green
        }
        catch [System.ServiceProcess.TimeoutException] {
            throw "The Setu Windows service did not start within 20 seconds. Check Windows Services, then try again."
        }
        catch {
            throw "Windows could not start the Setu service. Run start_setu.bat as Administrator. $($_.Exception.Message)"
        }
    }

    Write-Host "Use stop_setu.bat to stop it."
    return
}

$serverProcesses = @(Get-SetuServerProcesses -ProjectRoot $projectRoot -ExcludeProcessIds @($PID))
if ($serverProcesses.Count -gt 0) {
    $processIds = ($serverProcesses | ForEach-Object { $_.ProcessId }) -join ", "
    Write-Host "Setu is already running in another window or background process. PID(s): $processIds"
    Write-Host "Use stop_setu.bat to stop it before starting a fresh server."
    return
}

Write-Host "Starting Setu QR Tally Bridge..."
Write-Host "Open: http://${HostAddress}:$Port"
Write-Host "Press Ctrl+C in this window to stop the app."
& $pythonExe -m uvicorn app.main:app --host $HostAddress --port $Port
exit $LASTEXITCODE
