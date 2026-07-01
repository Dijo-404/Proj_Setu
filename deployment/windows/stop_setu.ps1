param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [string]$ServiceName = "SetuQrTallyBridge"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [IO.Path]::GetFullPath($ProjectDir).TrimEnd("\")
$pythonExe = [IO.Path]::GetFullPath((Join-Path $projectRoot ".venv\Scripts\python.exe"))
$startScript = [IO.Path]::GetFullPath((Join-Path $projectRoot "start_setu.bat"))
$stoppedAnything = $false

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

$setuProcesses = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.ExecutablePath -and
            [string]::Equals(
                [IO.Path]::GetFullPath($_.ExecutablePath),
                $pythonExe,
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            $_.CommandLine -match "(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:app(?:\s|$)"
        }
)

foreach ($process in $setuProcesses) {
    $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ParentProcessId)" -ErrorAction SilentlyContinue
    $launcherIsSetuBatch = (
        $launcher -and
        $launcher.Name -ieq "cmd.exe" -and
        $launcher.CommandLine -and
        (
            $launcher.CommandLine.IndexOf($startScript, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $launcher.CommandLine -match "(?i)start_setu\.bat"
        )
    )

    if ($launcherIsSetuBatch) {
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
