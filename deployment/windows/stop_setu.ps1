param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [string]$ServiceName = "SetuQrTallyBridge"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath($ProjectDir).TrimEnd("\")
$startScript = [IO.Path]::GetFullPath((Join-Path $projectRoot "start_setu.bat"))
$startHelper = [IO.Path]::GetFullPath((Join-Path $projectRoot "deployment\windows\start_setu.ps1"))
$processHelper = Join-Path $PSScriptRoot "server_processes.ps1"
$stoppedAnything = $false

if (-not (Test-Path -LiteralPath $processHelper)) {
    throw "The Setu process helper was not found: '$processHelper'."
}
. $processHelper

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne "Stopped") {
    Write-Host "Stopping the Setu Windows service..."
    try {
        Stop-Service -Name $ServiceName -Force
        $service.WaitForStatus("Stopped", [TimeSpan]::FromSeconds(20))
    }
    catch [System.ServiceProcess.TimeoutException] {
        throw "The Setu Windows service did not stop within 20 seconds. Check the service in Windows Services, then try again."
    }
    catch {
        throw "Windows could not stop the Setu service. Run this script as Administrator. $($_.Exception.Message)"
    }
    $stoppedAnything = $true
}

$setuProcesses = @(Get-SetuServerProcesses -ProjectRoot $projectRoot -ExcludeProcessIds @($PID))

foreach ($process in $setuProcesses) {
    $launcher = Get-SetuLauncherProcess -ServerProcess $process -StartScript $startScript -StartHelper $startHelper

    if ($launcher) {
        Write-Host "Stopping the existing Setu server window..."
        & taskkill.exe /PID $launcher.ProcessId /T /F | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Windows could not stop the existing Setu server window."
        }
    }
    elseif (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
        Write-Host "Stopping the existing Setu server process..."
        Stop-Process -Id $process.ProcessId -Force
    }
    $stoppedAnything = $true
}

if (-not $stoppedAnything) {
    Write-Host "No existing Setu server process was found."
}
