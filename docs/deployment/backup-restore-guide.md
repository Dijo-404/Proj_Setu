# Backup and Restore Guide

## Backup

1. Log in as admin.
2. Open `Maintenance`.
3. Click `Download backup`.
4. Store the downloaded `.db` file safely.

The backup uses SQLite's backup API, so WAL data is included.

Automatic verified backups run by default every 24 hours into `data/backups/`.
The app keeps the latest 14 backup files and opens every new backup for SQLite
integrity and foreign-key checks before retaining it. Configure these `.env`
values when needed:

```text
AUTOMATIC_BACKUPS_ENABLED=true
BACKUP_DIRECTORY=./data/backups
BACKUP_OFFSITE_DIRECTORY=
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_COUNT=14
```

Set `BACKUP_OFFSITE_DIRECTORY` to another drive or network share for a verified
off-machine copy. For an additional server-level backup such as Cobian
Reflector, include the whole project `data/` folder. Do not back up only
`data/setu.db` while the app is running, because SQLite may also have active
`setu.db-wal` and `setu.db-shm` sidecar files.

Also keep a separate copy of:

```text
.env
```

The `.env` file contains deployment settings such as the session secret, database URL, bootstrap admin defaults, and cookie security flag. It is not included inside the SQLite backup.

## Restore

1. Stop the Setu service or close the app window.
2. Copy the current `data/` folder to a safe location.
3. Replace `data/setu.db` with the backup file.
4. If a backup set also includes `setu.db-wal` and `setu.db-shm`, restore those sidecar files from the same backup point.
5. Restore `.env` only when moving to a new machine or recovering a lost config.
6. Start the Setu service or run `start_setu.bat`.
7. Log in and check Dashboard, Products, Serials, Reports, and Settings.

Do not restore while the app is running.

If the restored database came from another machine, confirm the Tally host, port, company profile, and `SESSION_COOKIE_SECURE` value before staff start scanning.
