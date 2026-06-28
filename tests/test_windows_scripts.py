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
