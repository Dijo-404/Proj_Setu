@echo off
setlocal
cd /d "%~dp0"

set "PROJECT_DIR=%CD%"
set "STOP_SCRIPT=%PROJECT_DIR%\deployment\windows\stop_setu.ps1"

if not exist "%STOP_SCRIPT%" (
    echo The Setu stop helper was not found:
    echo %STOP_SCRIPT%
    echo.
    echo Check that the deployment\windows folder is present, then try again.
    pause
    exit /b 1
)

echo Stopping Setu QR Tally Bridge...
powershell -NoProfile -ExecutionPolicy Bypass -File "%STOP_SCRIPT%" -ProjectDir "%PROJECT_DIR%" %*
set "STOP_EXIT=%ERRORLEVEL%"
echo.

if "%STOP_EXIT%"=="0" (
    echo Setu stop command completed.
) else (
    echo Setu could not be stopped. If Setu is installed as a Windows service,
    echo right-click stop_setu.bat and choose Run as administrator.
)

pause
exit /b %STOP_EXIT%
