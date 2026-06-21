# Backup and Restore Guide

## Backup

1. Log in as admin.
2. Open `Maintenance`.
3. Click `Download backup`.
4. Store the downloaded `.db` file safely.

The backup uses SQLite's backup API, so WAL data is included.

Also keep a separate copy of:

```text
.env
```

## Restore

1. Stop the Setu service.
2. Copy the current database file to a safe location.
3. Replace `data/setu.db` with the backup file.
4. Start the Setu service.
5. Log in and check Dashboard, Products, Serials, and Reports.

Do not restore while the app is running.

