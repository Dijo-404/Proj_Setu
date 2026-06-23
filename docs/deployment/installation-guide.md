# Installation Guide

## Target

Factory LAN deployment on the SERVER machine with Tally Prime running locally or reachable on the LAN.

## Prerequisites

- Windows 11 or Ubuntu 24.04 LTS
- Python 3.11 or newer
- Tally Prime configured as server on port `9000`
- Chrome or Edge on staff phones
- LAN hostname or static IP for the server

## Install

For a non-technical Windows install, run this from the project folder instead of typing the manual commands:

```powershell
.\setup.bat
```

It prompts for the first admin login, writes `.env`, installs dependencies, and can start the app when finished.

After setup, start the app anytime with:

```text
start_setu.bat
```

Manual install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```text
APP_SECRET_KEY=replace-with-a-long-random-secret
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=replace-before-first-use
DATABASE_URL=sqlite:///./data/setu.db
```

Start the app:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## First Login

Use the bootstrap admin from `.env`, then create named users from `Users`.

## First Configuration

1. Open `Settings`.
2. Enter Tally host, port, company, voucher type, ledger, and party names.
3. Create products with exact Tally stock item names.
4. Open `Tally Check`.
5. Mark each master checked only after comparing with Tally.
6. Enable Tally sync only after Tally Check is complete.

## Backup Reminder

Configure the server backup software to include the whole project `data/` folder
and a separate copy of `.env`. The app's Maintenance page also provides a
SQLite-safe database download for manual backups.

