from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from app.config import get_settings


@dataclass(frozen=True)
class BackupInfo:
    filename: str
    data: bytes


def sqlite_database_path() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Backup download is only available for SQLite deployments")
    return Path(url.replace("sqlite:///", "", 1)).resolve()


def create_sqlite_backup() -> BackupInfo:
    source_path = sqlite_database_path()
    if not source_path.exists():
        raise RuntimeError("SQLite database file does not exist yet")

    with NamedTemporaryFile(suffix=".db") as temp_file:
        source = sqlite3.connect(source_path)
        try:
            target = sqlite3.connect(temp_file.name)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        data = Path(temp_file.name).read_bytes()

    return BackupInfo(filename="setu-backup.db", data=data)
