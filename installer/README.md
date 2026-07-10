# Setuora Windows Installer

`SetuoraInstaller.exe` is an online bootstrap installer for a Windows 11 server.
It requests administrator access, installs Git for Windows when needed, clones or
updates the official Setuora repository, and launches the existing complete
`setup.bat` workflow.

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
go build -trimpath -ldflags="-s -w" -o ..\dist\SetuoraInstaller.exe .
```

Linux/macOS can cross-compile it with:

```bash
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o ../dist/SetuoraInstaller.exe .
```

The installer requires internet access. The generated executable is unsigned;
Windows SmartScreen may therefore ask the operator to confirm that it should run.

## Options

```text
SetuoraInstaller.exe --install-dir C:\Setuora --branch main
SetuoraInstaller.exe --skip-start
SetuoraInstaller.exe --skip-caddy
```
