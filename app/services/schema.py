from sqlalchemy import inspect, text

from app.database import engine


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    if "batches" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("batches")}
    with engine.begin() as connection:
        if "retry_count" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN retry_count INTEGER DEFAULT 0"))
        if "last_retry_at" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN last_retry_at DATETIME"))
        if "reason_code" not in columns:
            connection.execute(text("ALTER TABLE batches ADD COLUMN reason_code VARCHAR(80)"))
