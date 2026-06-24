from sqlalchemy import inspect, text

from app.database import engine


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    if "batches" not in inspector.get_table_names():
        return
    with engine.begin() as connection:
        columns = {column["name"] for column in inspector.get_columns("batches")}
        if "retry_count" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN retry_count INTEGER DEFAULT 0"))
        if "last_retry_at" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN last_retry_at DATETIME"))
        if "reason_code" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN reason_code VARCHAR(80)"))

        if "serials" in inspector.get_table_names():
            serial_columns = {column["name"] for column in inspector.get_columns("serials")}
            if "label_printed_at" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN label_printed_at DATETIME"))
            if "label_printed_by_id" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN label_printed_by_id INTEGER"))
