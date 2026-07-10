from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / "scripts"


def test_windows_workflows_are_grouped_under_scripts_directory():
    for filename in ("setup.bat", "start_setuora.bat", "stop_setuora.bat", "update.bat"):
        assert (WORKFLOWS_DIR / filename).is_file()
        assert not (PROJECT_ROOT / filename).exists()


def test_setup_skips_stop_helper_for_fresh_install():
    setup_script = (WORKFLOWS_DIR / "setup.bat").read_text(encoding="utf-8")

    stop_section = setup_script.split('Write-Section "Stop Existing Server"', 1)[1]
    stop_section = stop_section.split('Write-Section "Python"', 1)[0]

    assert "if (Test-Path $VenvPython)" in stop_section
    assert "Fresh installation; there is no existing Setuora server to stop." in stop_section


def test_requirements_pin_direct_starlette_import():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "starlette==1.3.1" in requirements


def test_lockfile_excludes_uvloop_on_windows_and_pins_windows_dependencies():
    lockfile = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")

    uvloop_line = next(line for line in lockfile.splitlines() if line.startswith("uvloop=="))
    assert "sys_platform != 'win32'" in uvloop_line
    assert "colorama==0.4.6 ; sys_platform == 'win32'" in lockfile


def test_setup_repairs_pip_and_checks_dependencies():
    setup_script = (WORKFLOWS_DIR / "setup.bat").read_text(encoding="utf-8")

    assert "function Ensure-Pip" in setup_script
    assert "$RequirementsLock = Join-Path $ProjectRoot \"requirements.lock\"" in setup_script
    assert "pip install --require-hashes -r $RequirementsLock" in setup_script
    assert "& $VenvPython -m ensurepip --upgrade" in setup_script
    assert "& $VenvPython -m pip check" in setup_script
    assert 'import uvicorn; from app.main import app; print(\'App import OK\')' in setup_script


def test_updater_never_uses_pull_or_rebase():
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")

    assert "& git pull " not in update_script
    assert "& git rebase " not in update_script
    assert "& git fetch --no-tags origin $branch" in update_script
    assert "& git merge --ff-only FETCH_HEAD" in update_script
    assert "git reset --hard FETCH_HEAD" not in update_script
    assert "Refusing to update because local source changes are present." in update_script
    assert "$worktreeChanges = @(& git status --porcelain)" in update_script


def test_updater_checks_service_permissions_before_fetching():
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")

    permission_check = update_script.index("if ($restartAsService -and -not (Test-AdminShell))")
    fetch = update_script.index("& git fetch --no-tags origin $branch")

    assert permission_check < fetch


def test_updater_repairs_pip_and_checks_dependencies():
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")

    assert "function Ensure-Pip" in update_script
    assert "& $VenvPython -m ensurepip --upgrade" in update_script
    assert "& $VenvPython -m pip install --upgrade pip" in update_script
    assert "& $VenvPython -m pip check" in update_script
    assert 'import uvicorn; from app.main import app; print(\'App import OK\')' in update_script


def test_updater_restarts_based_on_running_server_state():
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")

    assert "deployment\\windows\\server_processes.ps1" in update_script
    assert '$restartAsService = $service -and $service.Status -ne "Stopped"' in update_script
    assert "$runningSetuoraProcesses = @(Get-SetuoraServerProcesses" in update_script
    assert "$restartAsConsole = (-not $restartAsService) -and $runningSetuoraProcesses.Count -gt 0" in update_script
    assert 'Start-Process -FilePath $StartScript -ArgumentList @("-HostAddress", "$restartHostAddress", "-Port", "$restartPort")' in update_script
    assert "Setuora was not running before the update; leaving it stopped." in update_script


def test_start_script_uses_state_aware_windows_helper():
    start_script = (WORKFLOWS_DIR / "start_setuora.bat").read_text(encoding="utf-8")
    helper = (PROJECT_ROOT / "deployment" / "windows" / "start_setuora.ps1").read_text(
        encoding="utf-8"
    )

    assert "deployment\\windows\\start_setuora.ps1" in start_script
    assert "-HostAddress \"%HOST_ADDRESS%\" -Port \"%PORT%\"" in start_script
    assert "Get-Service -Name $ServiceName" in helper
    assert "Get-SetuoraServerProcesses" in helper
    assert "Setuora is already running in another window or background process." in helper


def test_start_helper_repairs_missing_dependencies_before_launch():
    helper = (PROJECT_ROOT / "deployment" / "windows" / "start_setuora.ps1").read_text(
        encoding="utf-8"
    )

    assert "function Ensure-AppDependencies" in helper
    assert "import uvicorn; from app.main import app" in helper
    assert "Set-Location $projectRoot" in helper
    assert "Test-AppDependencies -PythonExe $PythonExe -Quiet" in helper
    assert "& $PythonExe -m ensurepip --upgrade" in helper
    assert "$requirementsPath = Join-Path $projectRoot \"requirements.lock\"" in helper
    assert "& $PythonExe -m pip install --require-hashes -r $RequirementsPath" in helper
    assert "Ensure-AppDependencies -PythonExe $pythonExe -RequirementsPath $requirementsPath" in helper
    assert helper.index("Ensure-AppDependencies -PythonExe $pythonExe") < helper.index(
        "Get-Service -Name $ServiceName"
    )


def test_windows_services_use_the_least_privilege_localservice_account():
    installer = (PROJECT_ROOT / "deployment" / "windows" / "install_service.ps1").read_text(
        encoding="utf-8"
    )
    setup_script = (WORKFLOWS_DIR / "setup.bat").read_text(encoding="utf-8")

    assert 'ObjectName "NT AUTHORITY\\LocalService" ""' in installer
    assert '$CaddyServiceStartName = "NT AUTHORITY\\LocalService"' in setup_script
    assert "StartName = $CaddyServiceStartName" in setup_script
    assert "StartPassword = $null" in setup_script
    assert "sc.exe config $CaddyServiceName obj=" not in setup_script
    assert 'StartMode = "Manual"' in setup_script
    assert "Grant-LocalServiceAccess -Path $dataDir -Access \"M\"" in installer
    assert "Grant-LocalServiceAccess -Path $stateDir -Access \"M\"" in setup_script
    assert "Invoke-Nssm set $ServiceName Start SERVICE_DEMAND_START" in installer
    assert "Invoke-Nssm start $ServiceName" not in installer


def test_windows_workflows_can_run_from_the_unified_executable_without_pausing():
    for filename in ("setup.bat", "start_setuora.bat", "stop_setuora.bat", "update.bat"):
        script = (WORKFLOWS_DIR / filename).read_text(encoding="utf-8")

        assert 'if /I "%~1"=="--no-pause"' in script
        assert 'if not "%SETUORA_NO_PAUSE%"=="1" pause' in script


def test_windows_workflows_do_not_forward_no_pause_to_powershell_helpers():
    setup_script = (WORKFLOWS_DIR / "setup.bat").read_text(encoding="utf-8")
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")
    start_script = (WORKFLOWS_DIR / "start_setuora.bat").read_text(encoding="utf-8")
    stop_script = (WORKFLOWS_DIR / "stop_setuora.bat").read_text(encoding="utf-8")

    assert setup_script.index('set "SETUORA_SETUP_BAT=%~f0"') < setup_script.index("shift")
    assert update_script.index('set "SETUORA_UPDATE_BAT=%~f0"') < update_script.index("shift")
    assert '" %*' not in setup_script
    assert '" %*' not in update_script
    assert '" %*' not in stop_script
    assert "%1 %2 %3 %4 %5 %6 %7 %8 %9" in setup_script
    assert "%1 %2 %3 %4 %5 %6 %7 %8 %9" in update_script
    assert "%1 %2 %3 %4 %5 %6 %7 %8 %9" in stop_script
    assert "%~dp0.venv" not in start_script
    assert '"%PROJECT_DIR%\\.venv\\Scripts\\python.exe"' in start_script


def test_setup_does_not_start_services_or_caddy_by_default():
    setup_script = (WORKFLOWS_DIR / "setup.bat").read_text(encoding="utf-8")

    assert '[switch]$ConfigureCaddy' in setup_script
    assert 'Read-YesNo "Install and configure Caddy for HTTPS access from phones?" $false' in setup_script
    assert 'Read-YesNo "Start Setuora now in a new window?" $false' in setup_script
    assert 'Stop-Service -Name $CaddyServiceName -Force' in setup_script


def test_updater_restarts_the_optional_https_proxy_with_the_app_service():
    update_script = (WORKFLOWS_DIR / "update.bat").read_text(encoding="utf-8")

    assert '$CaddyServiceName = "SetuoraCaddy"' in update_script
    assert "Start-Service -Name $CaddyServiceName" in update_script


def test_target_server_preflight_is_available():
    preflight = (PROJECT_ROOT / "deployment" / "windows" / "production_preflight.ps1").read_text(
        encoding="utf-8"
    )

    assert "Assert-LocalServiceIdentity -ServiceName $AppServiceName" in preflight
    assert "https://$Address/health" in preflight
    assert "create_scheduled_backup" in preflight
    assert "git -C $projectRoot status --porcelain" in preflight


def test_stop_helper_detects_setuora_process_tree_not_loopback_socket():
    stop_helper = (
        PROJECT_ROOT / "deployment" / "windows" / "stop_setuora.ps1"
    ).read_text(encoding="utf-8")
    process_helper = (
        PROJECT_ROOT / "deployment" / "windows" / "server_processes.ps1"
    ).read_text(encoding="utf-8")

    assert "127.0.0.1" not in stop_helper
    assert "Get-SetuoraServerProcesses" in stop_helper
    assert "Get-SetuoraLauncherProcess" in stop_helper
    assert "start_setuora\\.bat" in process_helper
    assert "start_setuora\\.ps1" in process_helper
    assert "uvicorn.exe" in process_helper
    assert "Get-SetuoraServerLaunchInfo" in process_helper
