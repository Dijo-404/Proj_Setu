# Installation Guide

## Target

Factory LAN deployment on the SERVER machine with Tally Prime running locally or reachable on the LAN.

## Prerequisites

- Windows 11 or Ubuntu 24.04 LTS
- Python 3.11 for the current pinned dependency set
- Tally Prime configured as server on port `9000`
- Chrome or Edge on staff phones
- LAN hostname or static IP for the server

## Windows Install

For a non-technical Windows install, right-click `scripts\setup.bat`, choose **Run as
administrator**, or run it from an Administrator PowerShell:

```powershell
.\scripts\setup.bat
```

The helper:

- checks for Python 3.11 and can install it with `winget` when available
- creates `.venv`, `data/`, and `logs/`
- installs the hash-verified `requirements.lock`
- asks for the first admin username and password
- writes `.env`
- verifies that the app imports correctly
- installs Caddy with WinGet and configures LAN HTTPS when accepted
- creates an auto-start Caddy service and a local-subnet firewall rule
- exports Caddy's public root certificate for installation on staff phones
- can install the optional NSSM Windows service when run as Administrator
- can start the app when finished

After setup, start the app anytime with:

```text
scripts\start_setuora.bat
```

Use `scripts\start_setuora.bat --port 8001` if port `8000` is already in use.

Stop the app, including the Windows service when installed, with:

```text
scripts\stop_setuora.bat
```

Run `scripts\stop_setuora.bat` as Administrator when Setuora is installed as a Windows
service.

To pull the latest version from GitHub, update dependencies, and restart the
server, run:

```text
scripts\update.bat
```

Run the updater as Administrator when Setuora is installed as a Windows service.
The updater fetches and applies only a fast-forward Git update. It never
rebases and will not overwrite conflicting local code changes.

Pass `-SkipCaddy` to `scripts\setup.bat` if another reverse proxy already provides
HTTPS. When Caddy is configured, install
`deployment\caddy\setuora-caddy-root.crt` as a trusted CA certificate on every
phone that connects to Setuora.

## Manual Install

Linux/macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
cp .env.example .env
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
copy .env.example .env
```

Edit `.env`:

```text
APP_SECRET_KEY=replace-with-a-long-random-secret
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=replace-before-first-use
DATABASE_URL=sqlite:///./data/setuora.db
SESSION_COOKIE_SECURE=true
TRUSTED_HOSTS=setuora.local,127.0.0.1,localhost
```

Start the app:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For a production LAN deployment, open only through the configured HTTPS proxy:

```text
https://setuora.local
```

## First Login

If `scripts\setup.bat` created `.env`, use the admin login printed at the end of setup. If you copied `.env.example`, use the bootstrap admin from `.env`, then create named users from `Users`.

The app refuses to initialize its first administrator with an empty, placeholder,
or default password. Replace every placeholder before starting it.

Changing bootstrap values after the database exists does not update an existing user. Use the `Users` page for normal user administration.

## First Configuration

1. Open `Settings`.
2. Add or activate a company profile.
3. Enter exact Tally host, port, company, voucher type, ledger, GST, round-off, and party names.
4. Leave sync disabled until validation is complete.
5. Create products with exact Tally stock item names.
6. Open `Tally Check`.
7. Mark each master checked only after comparing with Tally.
8. Download a purchase, sale, or sales-return batch XML and validate it in the real Tally company.
9. Enable Tally sync only after Tally Check is complete.

Switching the active company disables sync until that company's masters are checked.

## Health Check

With the app running, open:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{ "status": "ok" }
```

## Backup Reminder

Setuora creates verified automatic backups into `data/backups/` by default. For
off-machine protection, set `BACKUP_OFFSITE_DIRECTORY` in `.env` to another
drive or network share and confirm the Maintenance page shows the latest copied
backup.

If server backup software is also used, include the whole project `data/`
folder, a separate copy of `.env`, and `deployment/caddy/state` when Caddy is
used. The Caddy state contains private keys and must not be distributed. The
app's Maintenance page also provides a SQLite-safe database download for manual
backups.

## Test Reminder

Run tests from a Python 3.11 environment:

```bash
python -m pytest -q
```

Expected current result:

```text
66 passed
```
