# Setu QR Tally Bridge

Setu is a LAN-first QR transaction bridge for Tally Prime. It lets staff scan product QR codes from phones, keeps serial-level history locally, and syncs supported stock movements to Tally through its XML gateway.

## Current Features

- Role-based login for admin, purchase, sales, and audit users
- Product master with HSN, GST, unit, default rate, and exact Tally stock item name
- Bulk QR serial generation and printable/PDF labels with QR plus serial number only
- Receive, sale, audit, sales return, purchase return, stock issue, and QR replacement workflows
- Batch pricing, GST split, round off, and voucher preview before submit
- Tally XML generation for receive and sale batches
- Tally Check screen for exact-name master readiness
- Pending sync queue, manual retry, and automatic retry worker
- Audit reconciliation for verified, missing, and extra serials
- CSV/XLSX reports and PDF audit reports
- SQLite-safe backup download and restore procedure

## Prerequisites

- Python 3.11 or newer
- Tally Prime installed and running on the server machine or reachable on the LAN
- Chrome or Edge for staff phones
- For phone camera use over LAN: HTTPS reverse proxy later, usually Caddy plus a local certificate

## Quick Windows Setup For Non-Technical Users

On the Windows server, double-click:

```text
setup.bat
```

The setup helper will check/install Python if possible, create `.venv`, install packages, ask for the first admin username/password, create `.env`, run a smoke test, and offer to start the app.

After setup, start the app anytime with:

```powershell
.\start_setu.ps1
```

If Windows blocks PowerShell scripts, use `setup.bat`; it starts PowerShell with the required one-time bypass for this setup run.

## 1. Open The Project Folder

```bash
cd /home/dj/Projects/Proj_Setu
```

On Windows, use the folder where this project is copied, for example:

```powershell
cd C:\Setu
```

## 2. Create A Virtual Environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If `pip` is missing on Linux, install it with your OS package manager, then rerun the command.

## 4. Create The Environment File

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
copy .env.example .env
```

Open `.env` and update these before real use:

```text
APP_SECRET_KEY=replace-with-a-long-random-secret
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=change-this-password
DATABASE_URL=sqlite:///./data/setu.db
```

For first local testing, the example values work, but do not use the default secret/password for production.

## 5. Start The App

Development mode:

```bash
uvicorn app.main:app --reload
```

Production-style local run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 6. First Login

Default login from `.env.example`:

```text
username: admin
password: admin123
```

After logging in:

1. Open `Users`.
2. Create named users for purchase, sales, auditor, and admin roles.
3. Disable or change the bootstrap admin password before production.

## 7. Basic Setup Inside The App

Do this in order:

1. Open `Settings`.
2. Enter Tally host, port, company name, voucher type names, ledger names, and default party.
3. Open `Products`.
4. Create products using the exact Tally stock item names.
5. Generate QR serials for products.
6. Open `Tally Check`.
7. Mark each required Tally master as checked only after confirming the exact spelling in Tally.
8. Keep Tally sync disabled until Tally Check has no missing or unchecked items.

## 8. Normal Workflow

Receive stock:

1. Open `Receive`.
2. Enter supplier/reference.
3. Scan serials.
4. Check the voucher preview.
5. Submit the batch.

Sell stock:

1. Open `Sale`.
2. Enter customer/reference.
3. Scan in-stock serials.
4. Check pricing, GST, round off, and final value.
5. Submit the batch.

Audit stock:

1. Open `Audit`.
2. Enter location/reference.
3. Scan physical stock.
4. Submit the audit.
5. Review verified, missing, and extra findings.

Returns and issue:

- `Sales return`: scan sold items returned by customer.
- `Purchase return`: scan in-stock items returned to supplier.
- `Issue`: scan in-stock items issued for sample, marketing, office use, production use, or free distribution.

QR replacement:

1. Open `QR Replace`.
2. Enter the damaged/old serial.
3. Leave new serial blank to auto-generate, or enter a new serial manually.
4. Print the new label.

## 9. Tally Integration

Tally sync is disabled by default.

Before enabling sync:

1. In Tally Prime, open the target company.
2. Enable Tally as a server on port `9000`.
3. Confirm inventory is maintained.
4. Confirm accounts and inventory are integrated.
5. In Setu, complete `Tally Check`.
6. Download `Tally XML` from a receive/sale batch and validate it against the real company.
7. Enable sync in `Settings`.

Supported live XML posting:

- Receive
- Sale

Implemented locally but intentionally not live-posted yet:

- Sales return
- Purchase return
- Stock issue

Those remain `PENDING_SYNC` until the exact Tally voucher XML for the client company is validated.

## 10. Reports And Exports

Use `Reports` for:

- Scan history
- Pending sync
- CSV export
- XLSX export

Use batch detail pages for:

- Tally XML download
- Sync attempt request/response details
- Audit PDF export

Use label pages for:

- Browser print
- QR label PDF download

## 11. Backup And Restore

Backup:

1. Open `Maintenance`.
2. Click `Download backup`.
3. Store the downloaded `.db` file safely.
4. Keep a separate copy of `.env`.

For scheduled server backups such as Cobian Reflector, include the whole
`data/` folder plus `.env`. The `data/` folder can contain SQLite sidecar files
such as `setu.db-wal` and `setu.db-shm` while the app is running.

Restore:

1. Stop the app/server.
2. Copy the current `data/` folder somewhere safe.
3. Replace `data/setu.db` with the backup file.
4. Start the app again.
5. Check Dashboard, Products, Serials, and Reports.

## 12. Run Tests

```bash
pytest
```

Or:

```bash
python -m pytest
```

Expected result:

```text
24 passed
```

## 13. LAN Phone Camera Setup

Phone camera access usually requires HTTPS when accessed from another device on the LAN.

Recommended production shape:

```text
Phone browser -> https://setu.local -> Caddy -> http://127.0.0.1:8000
```

Use:

- `docs/deployment/https-lan-guide.md`
- `deployment/caddy/Caddyfile.example`

Install the local certificate authority on staff phones if using `mkcert`.

## 14. Windows Service Setup

For production, run Setu as a Windows service using NSSM.

See:

- `docs/deployment/windows-service.md`
- `deployment/windows/install_service.ps1`

The service should run:

```text
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

Then Caddy/nginx can expose it over HTTPS on the LAN.

## 15. Useful Deployment Docs

- `docs/codex-windows-handoff.md`
- `docs/deployment/installation-guide.md`
- `docs/deployment/windows-service.md`
- `docs/deployment/https-lan-guide.md`
- `docs/deployment/user-manual.md`
- `docs/deployment/backup-restore-guide.md`
- `docs/deployment/tally-integration-guide.md`

## Troubleshooting

If login does not work:

- Confirm `.env` exists.
- Confirm the app was restarted after editing `.env`.
- Check the bootstrap username/password.

If camera does not open on phone:

- Use Chrome or Edge.
- Serve the app over HTTPS on the LAN.
- Confirm the browser has camera permission.

If Tally sync stays pending:

- Confirm Tally is open.
- Confirm Tally server mode is enabled on port `9000`.
- Open `Tally Check`.
- Confirm every required master is checked.
- Open the batch and review sync attempt details.

If the app fails to start:

- Confirm the virtual environment is active.
- Run `pip install -r requirements.txt`.
- Confirm port `8000` is free.
- Check that `data/` is writable.
