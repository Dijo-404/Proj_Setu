import sqlite3
from types import SimpleNamespace

import app.services.backup as backup_service
from app.services.backup import create_scheduled_backup, create_sqlite_backup, sqlite_database_path, verify_sqlite_backup


def test_create_sqlite_backup_uses_configured_database(tmp_path, monkeypatch):
    db_path = tmp_path / "setu.db"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("INSERT INTO sample (name) VALUES ('ok')")
    connection.commit()
    connection.close()

    monkeypatch.setattr(backup_service, "get_settings", lambda: SimpleNamespace(database_url=f"sqlite:///{db_path}"))
    assert sqlite_database_path() == db_path.resolve()
    backup = create_sqlite_backup()
    assert backup.data.startswith(b"SQLite format 3")


def test_create_sqlite_backup_rejects_corrupt_backup(tmp_path):
    corrupt = tmp_path / "bad.db"
    corrupt.write_bytes(b"not sqlite")

    try:
        verify_sqlite_backup(corrupt)
    except RuntimeError as exc:
        assert "integrity" in str(exc).lower() or "database" in str(exc).lower()
    else:
        raise AssertionError("Expected corrupt backup verification to fail")


def test_scheduled_backup_verifies_copies_offsite_and_prunes(tmp_path, monkeypatch):
    db_path = tmp_path / "setu.db"
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    connection.execute("CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))")
    connection.execute("INSERT INTO parent (id) VALUES (1)")
    connection.execute("INSERT INTO child (parent_id) VALUES (1)")
    connection.commit()
    connection.close()

    backup_dir = tmp_path / "backups"
    offsite_dir = tmp_path / "offsite"
    monkeypatch.setattr(
        backup_service,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=f"sqlite:///{db_path}",
            backup_directory=str(backup_dir),
            backup_offsite_directory=str(offsite_dir),
            backup_retention_count=2,
        ),
    )

    first = create_scheduled_backup()
    second = create_scheduled_backup()
    third = create_scheduled_backup()

    assert first.path.exists() is False
    assert second.path.exists()
    assert third.path.exists()
    assert third.offsite_path is not None
    assert third.offsite_path.exists()
    verify_sqlite_backup(third.path)
    verify_sqlite_backup(third.offsite_path)
    assert len(list(backup_dir.glob("setu-backup-*.db"))) == 2
    assert len(list(offsite_dir.glob("setu-backup-*.db"))) == 2
