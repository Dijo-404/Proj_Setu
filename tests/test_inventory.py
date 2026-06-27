from sqlalchemy import select, update

from app.models import BatchType, InventoryTransaction, Product, Serial, SerialStatus, TransactionType, User
from app.services.inventory import InventoryError, add_serial_to_batch, apply_batch_statuses, create_batch, generate_serials


def test_receive_generated_serial(db_session):
    user = User(username="purchase", password_hash="x", role="purchase")
    product = Product(
        product_code="SG001",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1)[0]
    batch = create_batch(db_session, user, BatchType.RECEIVE, "Supplier", "")
    item = add_serial_to_batch(db_session, batch, user, serial.serial_number)
    assert item.serial.status == SerialStatus.GENERATED.value


def test_submit_aborts_when_serial_grabbed_concurrently(db_session):
    user = User(username="sales-race", password_hash="x", role="sales")
    product = Product(
        product_code="SG099",
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

    db_session.execute(
        update(Serial).where(Serial.id == serial.id).values(status=SerialStatus.SOLD.value)
        .execution_options(synchronize_session=False)
    )

    try:
        apply_batch_statuses(db_session, batch, user)
        assert False, "stale claim should abort"
    except InventoryError:
        pass
    assert batch.status == "DRAFT"
    assert db_session.scalar(select(InventoryTransaction).where(InventoryTransaction.batch_id == batch.id)) is None


def test_serial_cannot_be_added_to_two_open_batches(db_session):
    user = User(username="sales-dup", password_hash="x", role="sales")
    product = Product(
        product_code="SG098",
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
    batch_a = create_batch(db_session, user, BatchType.SALE, "Customer A", "")
    batch_b = create_batch(db_session, user, BatchType.SALE, "Customer B", "")
    add_serial_to_batch(db_session, batch_a, user, serial.serial_number)

    try:
        add_serial_to_batch(db_session, batch_b, user, serial.serial_number)
        assert False, "serial already in an open batch must be rejected"
    except InventoryError as exc:
        assert "another open batch" in str(exc)


def test_sale_rejects_generated_serial(db_session):
    user = User(username="sales", password_hash="x", role="sales")
    product = Product(
        product_code="SG002",
        product_name="Chilli",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Chilli",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1)[0]
    batch = create_batch(db_session, user, BatchType.SALE, "Customer", "")
    try:
        add_serial_to_batch(db_session, batch, user, serial.serial_number)
    except InventoryError:
        assert True
    else:
        assert False


def test_purchase_batch_logs_purchase_transaction(db_session):
    user = User(username="purchase2", password_hash="x", role="purchase")
    product = Product(
        product_code="SG004",
        product_name="Turmeric",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Turmeric",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1)[0]
    batch = create_batch(db_session, user, BatchType.PURCHASE, "Supplier", "")
    add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)
    txn = db_session.scalar(select(InventoryTransaction).where(InventoryTransaction.serial_id == serial.id))
    assert serial.status == SerialStatus.IN_STOCK.value
    assert txn.transaction_type == TransactionType.PURCHASE.value
    assert txn.status_from == SerialStatus.GENERATED.value
    assert txn.status_to == SerialStatus.IN_STOCK.value
