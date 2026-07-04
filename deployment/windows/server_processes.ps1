function Test-PathEquals {
    param(
        [AllowNull()][string]$Left,
        [AllowNull()][string]$Right
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }

    return [string]::Equals(
        [IO.Path]::GetFullPath($Left),
        [IO.Path]::GetFullPath($Right),
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Test-SetuServerProcess {
    param(
        [Parameter(Mandatory=$true)]$Process,
        [Parameter(Mandatory=$true)][string]$ProjectRoot
    )

    $pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $uvicornExe = Join-Path $ProjectRoot ".venv\Scripts\uvicorn.exe"
    $commandLine = $Process.CommandLine

    if (-not $Process.ExecutablePath -or [string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    if (Test-PathEquals $Process.ExecutablePath $pythonExe) {
        return $commandLine -match "(?i)(?:^|\s)-m\s+uvicorn\s+app\.main:app(?:\s|$)"
    }

    if (Test-PathEquals $Process.ExecutablePath $uvicornExe) {
        return $commandLine -match "(?i)(?:^|\s)app\.main:app(?:\s|$)"
    }

    return $false
}

function Get-SetuServerProcesses {
    param(
        [Parameter(Mandatory=$true)][string]$ProjectRoot,
        [int[]]$ExcludeProcessIds = @()
    )

    $normalizedProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd("\")

    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $ExcludeProcessIds -notcontains [int]$_.ProcessId -and
                (Test-SetuServerProcess -Process $_ -ProjectRoot $normalizedProjectRoot)
            }
    )
}

function Get-SetuProcessById {
    param([uint32]$ProcessId)

    if ($ProcessId -eq 0) {
        return $null
    }

    $matches = @(Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    if ($matches.Count -gt 0) {
        return $matches[0]
    }

    return $null
}

function Test-SetuBatchLauncher {
    param(
        [AllowNull()]$Process,
        [Parameter(Mandatory=$true)][string]$StartScript
    )

    if (-not $Process -or $Process.Name -ine "cmd.exe" -or [string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $false
    }

    return (
        $Process.CommandLine.IndexOf($StartScript, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $Process.CommandLine -match "(?i)start_setu\.bat"
    )
}

function Test-SetuPowerShellLauncher {
    param(
        [AllowNull()]$Process,
        [Parameter(Mandatory=$true)][string]$StartHelper
    )

    if (
        -not $Process -or
        ($Process.Name -ine "powershell.exe" -and $Process.Name -ine "pwsh.exe") -or
        [string]::IsNullOrWhiteSpace($Process.CommandLine)
    ) {
        return $false
    }

    return (
        $Process.CommandLine.IndexOf($StartHelper, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $Process.CommandLine -match "(?i)start_setu\.ps1"
    )
}

function Get-SetuLauncherProcess {
    param(
        [Parameter(Mandatory=$true)]$ServerProcess,
        [Parameter(Mandatory=$true)][string]$StartScript,
        [Parameter(Mandatory=$true)][string]$StartHelper
    )

    $parent = Get-SetuProcessById -ProcessId $ServerProcess.ParentProcessId
    if (-not $parent) {
        return $null
    }

    if (Test-SetuBatchLauncher -Process $parent -StartScript $StartScript) {
        return $parent
    }

    if (Test-SetuPowerShellLauncher -Process $parent -StartHelper $StartHelper) {
        $grandparent = Get-SetuProcessById -ProcessId $parent.ParentProcessId
        if (Test-SetuBatchLauncher -Process $grandparent -StartScript $StartScript) {
            return $grandparent
        }

        return $parent
    }

    return $null
}

function Get-SetuCommandArgument {
    param(
        [Parameter(Mandatory=$true)][string]$CommandLine,
        [Parameter(Mandatory=$true)][string]$Name
    )

    $escapedName = [regex]::Escape($Name)
    $pattern = '(?i)(?:^|\s)--{0}(?:\s+|=)(?:"([^"]+)"|''([^'']+)''|([^\s]+))' -f $escapedName
    $match = [regex]::Match($CommandLine, $pattern)

    if (-not $match.Success) {
        return $null
    }

    foreach ($groupIndex in 1..3) {
        if ($match.Groups[$groupIndex].Success) {
            return $match.Groups[$groupIndex].Value
        }
    }

    return $null
}

function Get-SetuServerLaunchInfo {
    param(
        [Parameter(Mandatory=$true)]$Process,
        [string]$DefaultHostAddress = "127.0.0.1",
        [int]$DefaultPort = 8000
    )

    $hostAddress = Get-SetuCommandArgument -CommandLine $Process.CommandLine -Name "host"
    if ([string]::IsNullOrWhiteSpace($hostAddress)) {
        $hostAddress = $DefaultHostAddress
    }

    $port = $DefaultPort
    $portValue = Get-SetuCommandArgument -CommandLine $Process.CommandLine -Name "port"
    if (-not [string]::IsNullOrWhiteSpace($portValue)) {
        $parsedPort = 0
        if ([int]::TryParse($portValue, [ref]$parsedPort)) {
            $port = $parsedPort
        }
    }

    return [pscustomobject]@{
        HostAddress = $hostAddress
        Port = $port
        ProcessId = $Process.ProcessId
    }
}
