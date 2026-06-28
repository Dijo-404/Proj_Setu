from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Batch, BatchItem, Product, Serial, StorageLocation, User
from app.services.schema import _rebuild_sqlite_inventory_tables


def test_inventory_table_rebuild_preserves_rows_and_adds_all_foreign_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        user = User(username="admin", password_hash="x", role="admin")
        product = Product(
            product_code="MIG001",
            product_name="Migration Product",
            hsn="1",
            gst_rate=5,
            unit="Pcs",
            default_rate=10,
            tally_stock_item_name="Migration Product",
        )
        location = StorageLocation(
            code="MIG-A-1",
            warehouse="MAIN",
            zone="A",
            section="1",
            rack="R1",
            shelf="S1",
            bin="B1",
        )
        db.add_all([user, product, location])
        db.flush()
        serial = Serial(
            serial_number="MIG001-000001",
            product_id=product.id,
            status="IN_STOCK",
            label_printed_by_id=user.id,
            location_id=location.id,
        )
        batch = Batch(
            batch_number="SAL-MIG-0001",
            batch_type="SALE",
            user_id=user.id,
        )
        db.add_all([serial, batch])
        db.flush()
        db.add(
            BatchItem(
                batch_id=batch.id,
                serial_id=serial.id,
                shelf_location_id=location.id,
                shelf_verified_by_id=user.id,
            )
        )
        db.commit()

    _rebuild_sqlite_inventory_tables(engine)

    inspector = inspect(engine)
    serial_foreign_keys = {
        column
        for key in inspector.get_foreign_keys("serials")
        for column in key["constrained_columns"]
    }
    item_foreign_keys = {
        column
        for key in inspector.get_foreign_keys("batch_items")
        for column in key["constrained_columns"]
    }
    transaction_targets = {
        key["referred_table"] for key in inspector.get_foreign_keys("inventory_transactions")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM serials")) == 1
        assert connection.scalar(text("SELECT count(*) FROM batch_items")) == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []

    assert {"product_id", "replaced_by_id", "label_printed_by_id", "location_id"} <= serial_foreign_keys
    assert {"batch_id", "serial_id", "shelf_location_id", "shelf_verified_by_id"} <= item_foreign_keys
    assert "serials" in transaction_targets
