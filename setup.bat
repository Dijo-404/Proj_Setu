@echo off
setlocal
cd /d "%~dp0"
set "SETU_SETUP_BAT=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $path=$env:SETU_SETUP_BAT; $marker='### POWERSHELL SETUP SCRIPT ###'; $raw=Get-Content -Raw -LiteralPath $path; $start=$raw.LastIndexOf($marker); if ($start -lt 0) { throw 'Embedded setup script marker not found.' }; $code=$raw.Substring($start + $marker.Length); & ([scriptblock]::Create($code)) @args" %*
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
if not "%SETUP_EXIT%"=="0" echo Setup did not complete successfully.
pause
exit /b %SETUP_EXIT%

### POWERSHELL SETUP SCRIPT ###
param(
    [int]$Port = 8000,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $env:SETU_SETUP_BAT
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$StartScript = Join-Path $ProjectRoot "start_setu.bat"
$EnvPath = Join-Path $ProjectRoot ".env"
$DataDir = Join-Path $ProjectRoot "data"
$LogsDir = Join-Path $ProjectRoot "logs"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Read-Default {
    param(
        [string]$Prompt,
        [string]$Default
    )

    $answer = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($answer)) {
        return $Default
    }
    return $answer.Trim()
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$Default = $true
    )

    $suffix = if ($Default) { "Y/n" } else { "y/N" }
    while ($true) {
        $answer = Read-Host "$Prompt [$suffix]"
        if ([string]::IsNullOrWhiteSpace($answer)) {
            return $Default
        }

        switch ($answer.Trim().ToLowerInvariant()) {
            "y" { return $true }
            "yes" { return $true }
            "n" { return $false }
            "no" { return $false }
            default { Write-Host "Please answer yes or no." -ForegroundColor Yellow }
        }
    }
}

function ConvertFrom-SecureText {
    param([System.Security.SecureString]$Secure)

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function New-RandomSecret {
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }

    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Read-Password {
    param([string]$Username)

    while ($true) {
        Write-Host "Choose a password for the first admin user '$Username'."
        Write-Host "Leave it blank to let this setup generate one for you."
        $first = ConvertFrom-SecureText (Read-Host "Admin password" -AsSecureString)
        if ([string]::IsNullOrWhiteSpace($first)) {
            return New-RandomSecret -ByteCount 14
        }

        $second = ConvertFrom-SecureText (Read-Host "Confirm admin password" -AsSecureString)
        if ($first -eq $second) {
            if ($first.Length -lt 8) {
                $useShort = Read-YesNo "That password is short. Use it anyway?" $false
                if (-not $useShort) {
                    continue
                }
            }
            return $first
        }

        Write-Host "Passwords did not match. Please try again." -ForegroundColor Yellow
    }
}

function Get-PythonCommand {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.11") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        $versionArgs = @($candidate.Args) + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")
        try {
            & $candidate.Exe @versionArgs | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Install-PythonWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    Write-Host "Python 3.11+ was not found. Trying to install Python 3.11 using winget..."
    & winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Python {
    $python = Get-PythonCommand
    if ($python) {
        return $python
    }

    $install = Read-YesNo "Python 3.11 or newer is required. Install Python 3.11 now with winget?" $true
    if ($install -and (Install-PythonWithWinget)) {
        $python = Get-PythonCommand
        if ($python) {
            return $python
        }
    }

    throw "Python 3.11+ was not found. Install it from https://www.python.org/downloads/ and run setup again."
}

function Ensure-Venv {
    param($Python)

    if (Test-Path $VenvPython) {
        Write-Host "Virtual environment already exists."
        return
    }

    Write-Host "Creating Python virtual environment..."
    $args = @($Python.Args) + @("-m", "venv", $VenvDir)
    & $Python.Exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the virtual environment."
    }
}

function Install-Dependencies {
    Write-Host "Installing Python packages. This can take a few minutes..."
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upgrade pip."
    }

    & $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install project dependencies."
    }
}

function Write-EnvFile {
    $existingDatabase = Test-Path (Join-Path $DataDir "setu.db")
    if ($existingDatabase) {
        Write-Host "Existing data\setu.db found. Changing bootstrap admin details will not change existing users." -ForegroundColor Yellow
    }

    $appName = Read-Default "App display name" "Setu QR Tally Bridge"
    $adminUser = Read-Default "First admin username" "admin"
    $adminPassword = Read-Password $adminUser
    $sessionTimeout = Read-Default "Login session timeout in minutes" "480"
    $secureCookie = Read-YesNo "Will this app be opened only through HTTPS right now?" $false
    $databaseUrl = "sqlite:///./data/setu.db"
    $secret = New-RandomSecret

    $secureCookieText = if ($secureCookie) { "true" } else { "false" }
    $lines = @(
        "APP_NAME=$appName",
        "APP_SECRET_KEY=$secret",
        "DATABASE_URL=$databaseUrl",
        "SESSION_TIMEOUT_MINUTES=$sessionTimeout",
        "BOOTSTRAP_ADMIN_USERNAME=$adminUser",
        "BOOTSTRAP_ADMIN_PASSWORD=$adminPassword",
        "SESSION_COOKIE_SECURE=$secureCookieText",
        "LOGIN_MAX_ATTEMPTS=8",
        "LOGIN_LOCKOUT_MINUTES=15"
    )

    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8

    return @{
        Username = $adminUser
        Password = $adminPassword
        SecureCookie = $secureCookieText
    }
}

function Ensure-EnvFile {
    if (Test-Path $EnvPath) {
        $keepExisting = Read-YesNo ".env already exists. Keep it as-is?" $true
        if ($keepExisting) {
            return $null
        }
    }

    return Write-EnvFile
}

function Test-AdminShell {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Offer-ServiceInstall {
    $installService = Read-YesNo "Install Setu as a Windows service now? This needs Administrator PowerShell and NSSM." $false
    if (-not $installService) {
        return
    }

    if (-not (Test-AdminShell)) {
        Write-Host "Skipping service install because this window is not running as Administrator." -ForegroundColor Yellow
        Write-Host "Run setup.bat again as Administrator if you want the service installed."
        return
    }

    $defaultNssm = "C:\Tools\nssm\nssm.exe"
    $nssmPath = Read-Default "Path to nssm.exe" $defaultNssm
    if (-not (Test-Path $nssmPath)) {
        Write-Host "NSSM was not found at '$nssmPath'. Download NSSM, then run the service installer later." -ForegroundColor Yellow
        return
    }

    $serviceScript = Join-Path $ProjectRoot "deployment\windows\install_service.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $serviceScript -ProjectDir $ProjectRoot -NssmPath $nssmPath -Port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Windows service install failed."
    }
}

function Get-LocalIPv4 {
    $addresses = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
    foreach ($address in $addresses) {
        if ($address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not $address.ToString().StartsWith("169.254.")) {
            return $address.ToString()
        }
    }
    return $null
}

Write-Section "Setu Setup"
Write-Host "This setup will prepare Python, install packages, create .env, and optionally start the app."

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $DataDir, $LogsDir | Out-Null

Write-Section "Python"
$python = Ensure-Python
Ensure-Venv $python

Write-Section "Dependencies"
Install-Dependencies

Write-Section "Configuration"
$credentials = Ensure-EnvFile

Write-Section "Smoke Test"
& $VenvPython -c "from app.main import app; print('App import OK')"
if ($LASTEXITCODE -ne 0) {
    throw "The app could not be imported. Check the error above."
}

Write-Section "Optional Service"
Offer-ServiceInstall

Write-Section "Done"
Write-Host "Setup completed successfully." -ForegroundColor Green
Write-Host "Local URL: http://127.0.0.1:$Port"
$lanIp = Get-LocalIPv4
if ($lanIp) {
    Write-Host "LAN test URL: http://${lanIp}:$Port"
}
Write-Host "Backup reminder: include the whole data folder and .env in scheduled server backups."
if ($credentials) {
    Write-Host ""
    Write-Host "First admin login:"
    Write-Host "  Username: $($credentials.Username)"
    Write-Host "  Password: $($credentials.Password)"
    Write-Host "Keep this password somewhere safe. It is only shown during setup."
}

if (-not $SkipStart) {
    $startNow = Read-YesNo "Start Setu now in a new window?" $true
    if ($startNow) {
        Start-Process -FilePath $StartScript -ArgumentList @("-Port", "$Port")
        Start-Sleep -Seconds 2
        Start-Process "http://127.0.0.1:$Port"
    }
}
