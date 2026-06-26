from app.models import BatchStatus, BatchType, Product, SerialStatus, User
from app.services import tally as tally_service
from app.services.inventory import add_serial_to_batch, apply_batch_statuses, create_batch, generate_serials
from app.services.tally import sync_batch


def test_retry_sync_records_retry_metadata_when_still_queued(db_session):
    user = User(username="sales", password_hash="x", role="sales")
    product = Product(
        product_code="SG030",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, user, BatchType.SALE, "Customer", "")
    add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)
    db_session.commit()
    sync_batch(db_session, batch)
    assert batch.status == BatchStatus.PENDING_SYNC.value
    assert batch.retry_count == 0
    sync_batch(db_session, batch)
    assert batch.status == BatchStatus.PENDING_SYNC.value
    assert batch.retry_count == 1
    assert batch.last_retry_at is not None


def test_already_synced_batch_is_not_posted_again(db_session, monkeypatch):
    user = User(username="sales2", password_hash="x", role="sales")
    product = Product(
        product_code="SG031",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, user, BatchType.SALE, "Customer", "")
    add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)
    batch.status = BatchStatus.SYNCED.value
    db_session.commit()

    calls = {"count": 0}

    def fail_if_posted(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("post_to_tally must not run for an already-synced batch")

    monkeypatch.setattr(tally_service, "post_to_tally", fail_if_posted)
    sync_batch(db_session, batch)
    assert calls["count"] == 0
    assert batch.status == BatchStatus.SYNCED.value
