param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$NssmPath,
    [string]$ServiceName = "SetuQrTallyBridge",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$pythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "data") | Out-Null

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Virtual-environment Python was not found at '$pythonExe'."
}
if (-not (Test-Path -LiteralPath $NssmPath)) {
    throw "NSSM was not found at '$NssmPath'."
}

function Invoke-Nssm {
    & $NssmPath @args | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM command failed: nssm $($args -join ' ')"
    }
}

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existingService) {
    Invoke-Nssm install $ServiceName $pythonExe
}
elseif ($existingService.Status -ne "Stopped") {
    Invoke-Nssm stop $ServiceName
}

Invoke-Nssm set $ServiceName Application $pythonExe
Invoke-Nssm set $ServiceName AppParameters "-m uvicorn app.main:app --host 127.0.0.1 --port $Port"
Invoke-Nssm set $ServiceName AppDirectory $ProjectDir
Invoke-Nssm set $ServiceName AppStdout (Join-Path $logDir "setu-out.log")
Invoke-Nssm set $ServiceName AppStderr (Join-Path $logDir "setu-err.log")
Invoke-Nssm set $ServiceName AppRotateFiles 1
Invoke-Nssm set $ServiceName AppRotateBytes 10485760
Invoke-Nssm set $ServiceName Start SERVICE_AUTO_START
Invoke-Nssm set $ServiceName AppExit Default Restart
Invoke-Nssm start $ServiceName

