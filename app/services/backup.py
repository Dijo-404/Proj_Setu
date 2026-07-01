from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from app.config import PROJECT_ROOT, get_settings


@dataclass(frozen=True)
class BackupInfo:
    filename: str
    data: bytes


@dataclass(frozen=True)
class BackupFileInfo:
    filename: str
    path: Path
    size_bytes: int
    verified_at: datetime
    offsite_path: Path | None = None


@dataclass(frozen=True)
class BackupStatus:
    enabled: bool
    directory: Path
    interval_hours: int
    retention_count: int
    latest_backup: Path | None
    latest_backup_size_bytes: int | None
    offsite_directory: Path | None
    offsite_latest_backup: Path | None


def sqlite_database_path() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Backup download is only available for SQLite deployments")
    return Path(url.replace("sqlite:///", "", 1)).resolve()


def resolve_configured_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def verify_sqlite_backup(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Backup file does not exist: {path}")
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"SQLite integrity check failed for backup: {integrity}")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"SQLite foreign-key check failed for backup: {violations[:5]}")
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"SQLite backup verification failed for {path}: {exc}") from exc
    finally:
        connection.close()


def _copy_sqlite_database(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(destination_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def create_sqlite_backup() -> BackupInfo:
    source_path = sqlite_database_path()
    if not source_path.exists():
        raise RuntimeError("SQLite database file does not exist yet")

    # NamedTemporaryFile keeps an open Windows handle that sqlite3 cannot reuse.
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "setu-backup.db"
        _copy_sqlite_database(source_path, temp_path)
        verify_sqlite_backup(temp_path)
        data = temp_path.read_bytes()

    return BackupInfo(filename="setu-backup.db", data=data)


def create_scheduled_backup() -> BackupFileInfo:
    source_path = sqlite_database_path()
    if not source_path.exists():
        raise RuntimeError("SQLite database file does not exist yet")

    settings = get_settings()
    backup_dir = resolve_configured_path(getattr(settings, "backup_directory", "./data/backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    filename = f"setu-backup-{stamp}.db"
    destination = backup_dir / filename
    temp_destination = backup_dir / f".{filename}.tmp"
    if temp_destination.exists():
        temp_destination.unlink()

    _copy_sqlite_database(source_path, temp_destination)
    verify_sqlite_backup(temp_destination)
    temp_destination.replace(destination)

    offsite_path = _copy_to_offsite(destination, filename, settings)
    _prune_backups(backup_dir, getattr(settings, "backup_retention_count", 14))
    offsite_dir = getattr(settings, "backup_offsite_directory", "").strip()
    if offsite_dir:
        _prune_backups(resolve_configured_path(offsite_dir), getattr(settings, "backup_retention_count", 14))

    return BackupFileInfo(
        filename=filename,
        path=destination,
        size_bytes=destination.stat().st_size,
        verified_at=datetime.now(timezone.utc),
        offsite_path=offsite_path,
    )


def backup_status() -> BackupStatus:
    settings = get_settings()
    backup_dir = resolve_configured_path(getattr(settings, "backup_directory", "./data/backups"))
    offsite_value = getattr(settings, "backup_offsite_directory", "").strip()
    offsite_dir = resolve_configured_path(offsite_value) if offsite_value else None
    latest = _latest_backup(backup_dir)
    offsite_latest = _latest_backup(offsite_dir) if offsite_dir else None
    return BackupStatus(
        enabled=getattr(settings, "automatic_backups_enabled", True),
        directory=backup_dir,
        interval_hours=max(1, int(getattr(settings, "backup_interval_hours", 24))),
        retention_count=max(1, int(getattr(settings, "backup_retention_count", 14))),
        latest_backup=latest,
        latest_backup_size_bytes=latest.stat().st_size if latest and latest.exists() else None,
        offsite_directory=offsite_dir,
        offsite_latest_backup=offsite_latest,
    )


def _copy_to_offsite(source: Path, filename: str, settings: object) -> Path | None:
    offsite_value = getattr(settings, "backup_offsite_directory", "").strip()
    if not offsite_value:
        return None

    offsite_dir = resolve_configured_path(offsite_value)
    offsite_dir.mkdir(parents=True, exist_ok=True)
    destination = offsite_dir / filename
    temp_destination = offsite_dir / f".{filename}.tmp"
    if temp_destination.exists():
        temp_destination.unlink()
    shutil.copy2(source, temp_destination)
    verify_sqlite_backup(temp_destination)
    temp_destination.replace(destination)
    return destination


def _backup_files(directory: Path | None) -> list[Path]:
    if not directory or not directory.exists():
        return []
    return sorted(directory.glob("setu-backup-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)


def _latest_backup(directory: Path | None) -> Path | None:
    files = _backup_files(directory)
    return files[0] if files else None


def _prune_backups(directory: Path, retention_count: int) -> None:
    keep = max(1, int(retention_count))
    for backup in _backup_files(directory)[keep:]:
        backup.unlink(missing_ok=True)
