from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_setup_skips_stop_helper_for_fresh_install():
    setup_script = (PROJECT_ROOT / "setup.bat").read_text(encoding="utf-8")

    stop_section = setup_script.split('Write-Section "Stop Existing Server"', 1)[1]
    stop_section = stop_section.split('Write-Section "Python"', 1)[0]

    assert "if (Test-Path $VenvPython)" in stop_section
    assert "Fresh installation; there is no existing Setu server to stop." in stop_section


def test_updater_never_uses_pull_or_rebase():
    update_script = (PROJECT_ROOT / "update.bat").read_text(encoding="utf-8")

    assert "& git pull " not in update_script
    assert "& git rebase " not in update_script
    assert "& git fetch --no-tags origin $branch" in update_script
    assert "& git merge --ff-only FETCH_HEAD" in update_script


def test_updater_checks_service_permissions_before_fetching():
    update_script = (PROJECT_ROOT / "update.bat").read_text(encoding="utf-8")

    permission_check = update_script.index("if ($restartAsService -and -not (Test-AdminShell))")
    fetch = update_script.index("& git fetch --no-tags origin $branch")

    assert permission_check < fetch


def test_updater_restarts_based_on_running_server_state():
    update_script = (PROJECT_ROOT / "update.bat").read_text(encoding="utf-8")

    assert "deployment\\windows\\server_processes.ps1" in update_script
    assert '$restartAsService = $service -and $service.Status -ne "Stopped"' in update_script
    assert "$runningSetuProcesses = @(Get-SetuServerProcesses" in update_script
    assert "$restartAsConsole = (-not $restartAsService) -and $runningSetuProcesses.Count -gt 0" in update_script
    assert 'Start-Process -FilePath $StartScript -ArgumentList @("-HostAddress", "$restartHostAddress", "-Port", "$restartPort")' in update_script
    assert "Setu was not running before the update; leaving it stopped." in update_script


def test_start_script_uses_state_aware_windows_helper():
    start_script = (PROJECT_ROOT / "start_setu.bat").read_text(encoding="utf-8")
    helper = (PROJECT_ROOT / "deployment" / "windows" / "start_setu.ps1").read_text(
        encoding="utf-8"
    )

    assert "deployment\\windows\\start_setu.ps1" in start_script
    assert "-HostAddress \"%HOST_ADDRESS%\" -Port \"%PORT%\"" in start_script
    assert "Get-Service -Name $ServiceName" in helper
    assert "Get-SetuServerProcesses" in helper
    assert "Setu is already running in another window or background process." in helper


def test_stop_helper_detects_setu_process_tree_not_loopback_socket():
    stop_helper = (
        PROJECT_ROOT / "deployment" / "windows" / "stop_setu.ps1"
    ).read_text(encoding="utf-8")
    process_helper = (
        PROJECT_ROOT / "deployment" / "windows" / "server_processes.ps1"
    ).read_text(encoding="utf-8")

    assert "127.0.0.1" not in stop_helper
    assert "Get-SetuServerProcesses" in stop_helper
    assert "Get-SetuLauncherProcess" in stop_helper
    assert "start_setu\\.bat" in process_helper
    assert "start_setu\\.ps1" in process_helper
    assert "uvicorn.exe" in process_helper
    assert "Get-SetuServerLaunchInfo" in process_helper
