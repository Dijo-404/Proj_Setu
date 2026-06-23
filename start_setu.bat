@echo off
setlocal
cd /d "%~dp0"

set "HOST_ADDRESS=127.0.0.1"
set "PORT=8000"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="-Port" (
    set "PORT=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--port" (
    set "PORT=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="/Port" (
    set "PORT=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="-HostAddress" (
    set "HOST_ADDRESS=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--host" (
    set "HOST_ADDRESS=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:args_done
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Setu is not set up yet. Run setup.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting Setu QR Tally Bridge...
echo Open: http://%HOST_ADDRESS%:%PORT%
echo Press Ctrl+C in this window to stop the app.
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host "%HOST_ADDRESS%" --port "%PORT%"
set "APP_EXIT=%ERRORLEVEL%"
echo.
if not "%APP_EXIT%"=="0" echo Setu stopped with error code %APP_EXIT%.
pause
exit /b %APP_EXIT%
