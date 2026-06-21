import sqlite3
from types import SimpleNamespace

import app.services.backup as backup_service
from app.services.backup import create_sqlite_backup, sqlite_database_path


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
