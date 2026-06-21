# Windows Service Guide

Use NSSM to run Setu automatically after reboot.

## Files

- Example install script: `deployment/windows/install_service.ps1`
- App command: `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`

## Steps

1. Install Python and dependencies.
2. Download `nssm.exe` and place it somewhere stable, for example `C:\Tools\nssm\nssm.exe`.
3. Open PowerShell as Administrator.
4. Run the install script with the correct paths.

```powershell
.\deployment\windows\install_service.ps1 `
  -ProjectDir "C:\Setu" `
  -NssmPath "C:\Tools\nssm\nssm.exe"
```

## Service Controls

```powershell
nssm status SetuQrTallyBridge
nssm restart SetuQrTallyBridge
nssm stop SetuQrTallyBridge
```

Logs should be written to:

```text
logs\setu-out.log
logs\setu-err.log
```

