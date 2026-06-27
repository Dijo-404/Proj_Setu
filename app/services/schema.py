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
            if "product_batch_number" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN product_batch_number VARCHAR(80)"))
            if "mfg_date" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN mfg_date DATE"))
            if "expiry_date" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN expiry_date DATE"))
            if "warehouse" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN warehouse VARCHAR(80)"))
            if "warehouse_level" not in serial_columns:
                connection.execute(
                    text(
                        "ALTER TABLE serials ADD COLUMN warehouse_level "
                        "VARCHAR(40) DEFAULT 'Company Warehouse'"
                    )
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_serials_warehouse_level ON serials (warehouse_level)")
                )
            if "location_id" not in serial_columns:
                connection.execute(text("ALTER TABLE serials ADD COLUMN location_id INTEGER"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_serials_location_id ON serials (location_id)"))

        if "batch_items" in inspector.get_table_names():
            item_columns = {column["name"] for column in inspector.get_columns("batch_items")}
            if "fefo_picked" not in item_columns:
                connection.execute(text("ALTER TABLE batch_items ADD COLUMN fefo_picked BOOLEAN DEFAULT 0"))
            if "shelf_location_id" not in item_columns:
                connection.execute(text("ALTER TABLE batch_items ADD COLUMN shelf_location_id INTEGER"))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_batch_items_shelf_location_id ON batch_items (shelf_location_id)")
                )
            if "shelf_verified_by_id" not in item_columns:
                connection.execute(text("ALTER TABLE batch_items ADD COLUMN shelf_verified_by_id INTEGER"))
            if "shelf_verified_at" not in item_columns:
                connection.execute(text("ALTER TABLE batch_items ADD COLUMN shelf_verified_at DATETIME"))

        if "products" in inspector.get_table_names():
            product_columns = {column["name"] for column in inspector.get_columns("products")}
            if "sales_discount_rate" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN sales_discount_rate FLOAT DEFAULT 0"))
            if "brand" not in product_columns:
                connection.execute(text("ALTER TABLE products ADD COLUMN brand VARCHAR(120)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_products_brand ON products (brand)"))
            if "shelf_verification_interval" not in product_columns:
                connection.execute(
                    text("ALTER TABLE products ADD COLUMN shelf_verification_interval INTEGER DEFAULT 1")
                )
            connection.execute(
                text(
                    "UPDATE products SET shelf_verification_interval = 1 "
                    "WHERE shelf_verification_interval IS NULL OR shelf_verification_interval < 1"
                )
            )

        if "users" in inspector.get_table_names():
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "deleted_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN deleted_at DATETIME"))
            if "must_change_password" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0"))

        if "storage_locations" in inspector.get_table_names():
            location_columns = {column["name"] for column in inspector.get_columns("storage_locations")}
            if "warehouse_level" not in location_columns:
                connection.execute(
                    text(
                        "ALTER TABLE storage_locations ADD COLUMN warehouse_level "
                        "VARCHAR(40) DEFAULT 'Company Warehouse'"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_storage_locations_warehouse_level "
                        "ON storage_locations (warehouse_level)"
                    )
                )

        if engine.dialect.name == "sqlite" and "stock_relocations" in inspector.get_table_names():
            for table_name in ("stock_relocations", "relocation_serials"):
                connection.execute(
                    text(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_update
                        BEFORE UPDATE ON {table_name}
                        BEGIN
                            SELECT RAISE(ABORT, 'Relocation history is permanent');
                        END
                        """
                    )
                )
                connection.execute(
                    text(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_delete
                        BEFORE DELETE ON {table_name}
                        BEGIN
                            SELECT RAISE(ABORT, 'Relocation history is permanent');
                        END
                        """
                    )
                )
