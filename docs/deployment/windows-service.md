# Windows Service Guide

Use NSSM to run Setu automatically after reboot. The easier path is to run `setup.bat` as Administrator and accept the optional service install when prompted. Use this guide when installing or repairing the service manually.

## Files

- Example install script: `deployment/windows/install_service.ps1`
- Default service name: `SetuQrTallyBridge`
- App command: `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`
- Logs: `logs\setu-out.log` and `logs\setu-err.log`

## Steps

1. Run `setup.bat` first so `.venv`, `.env`, `data\`, and `logs\` exist.
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

Restart the service after editing `.env`:

```powershell
nssm restart SetuQrTallyBridge
```

If Caddy is used for LAN HTTPS, keep the Setu service on `127.0.0.1:8000` and let Caddy expose the local HTTPS hostname.
