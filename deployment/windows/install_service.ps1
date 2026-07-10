param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$NssmPath,
    [string]$ServiceName = "SetuoraQrTallyBridge",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$pythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$logDir = Join-Path $ProjectDir "logs"
$dataDir = Join-Path $ProjectDir "data"
$localServiceSid = "*S-1-5-19"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

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

function Grant-LocalServiceAccess {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Access
    )

    & icacls.exe $Path /grant "${localServiceSid}:(OI)(CI)$Access" /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not grant LocalService $Access access to '$Path'."
    }
}

# The service can read application code but only write its database and logs.
Grant-LocalServiceAccess -Path $ProjectDir -Access "RX"
Grant-LocalServiceAccess -Path $dataDir -Access "M"
Grant-LocalServiceAccess -Path $logDir -Access "M"

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
Invoke-Nssm set $ServiceName AppStdout (Join-Path $logDir "setuora-out.log")
Invoke-Nssm set $ServiceName AppStderr (Join-Path $logDir "setuora-err.log")
Invoke-Nssm set $ServiceName AppRotateFiles 1
Invoke-Nssm set $ServiceName AppRotateBytes 10485760
Invoke-Nssm set $ServiceName Start SERVICE_DEMAND_START
Invoke-Nssm set $ServiceName AppExit Default Restart
Invoke-Nssm set $ServiceName AppThrottle 15000
Invoke-Nssm set $ServiceName AppRestartDelay 5000
# Never run the web application as LocalSystem. LocalService has no administrator
# privileges and only has write access to the runtime directories above.
Invoke-Nssm set $ServiceName ObjectName "NT AUTHORITY\LocalService" ""
