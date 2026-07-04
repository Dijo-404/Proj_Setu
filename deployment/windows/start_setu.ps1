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
$processHelper = Join-Path $PSScriptRoot "server_processes.ps1"

if (-not (Test-Path -LiteralPath $processHelper)) {
    throw "The Setu process helper was not found: '$processHelper'."
}
. $processHelper

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Setu is not set up yet. Run setup.bat first."
}

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
