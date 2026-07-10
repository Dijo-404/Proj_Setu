# Setuora Windows Installer

`Setuora.exe` is the single Windows control executable for a Windows 11 server.
It provides setup, start, stop, and update commands. Setup requests administrator
access, installs Git for Windows when needed, clones or updates the official
Setuora repository, and launches the complete `setup.bat` workflow without
starting the application automatically.

The setup workflow installs Python when needed, creates the virtual environment,
installs Python dependencies, creates or preserves `.env` and application data,
runs an import smoke test, offers Caddy HTTPS configuration, offers the Windows
service, and starts the application.

## Build

From this directory with Go installed:

```text
go test ./...
set GOOS=windows
set GOARCH=amd64
go build -trimpath -ldflags="-s -w" -o ..\dist\Setuora.exe .
```

Linux/macOS can cross-compile it with:

```bash
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o ../dist/Setuora.exe .
```

The installer requires internet access. The generated executable is unsigned;
Windows SmartScreen may therefore ask the operator to confirm that it should run.

## Options

```text
Setuora.exe setup --install-dir C:\Setuora --branch main
Setuora.exe setup --with-caddy
Setuora.exe start
Setuora.exe stop
Setuora.exe update
```
