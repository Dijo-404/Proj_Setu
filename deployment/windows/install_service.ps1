param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$NssmPath,
    [string]$ServiceName = "SetuQrTallyBridge",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $ProjectDir ".venv\Scripts\uvicorn.exe"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "data") | Out-Null

& $NssmPath install $ServiceName $pythonExe "app.main:app" "--host" "127.0.0.1" "--port" "$Port"
& $NssmPath set $ServiceName AppDirectory $ProjectDir
& $NssmPath set $ServiceName AppStdout (Join-Path $logDir "setu-out.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $logDir "setu-err.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760
& $NssmPath start $ServiceName

