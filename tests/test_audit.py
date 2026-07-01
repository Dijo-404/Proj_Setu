from sqlalchemy import select

from app.models import BatchType, InventoryTransaction, Product, SerialStatus, StorageLocation, TransactionType, User
from app.services.audit import reconcile_audit_batch
from app.services.inventory import add_serial_to_batch, apply_batch_statuses, create_batch, generate_serials
from app.services.shelf_verification import verify_pending_items_on_shelf


def test_audit_reconciliation_finds_verified_missing_and_extra(db_session):
    auditor = User(username="auditor", password_hash="x", role="auditor")
    product = Product(
        product_code="SG040",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([auditor, product])
    db_session.commit()
    in_stock = generate_serials(db_session, product, 2, initial_status=SerialStatus.IN_STOCK)
    sold = generate_serials(db_session, product, 1, initial_status=SerialStatus.SOLD)[0]
    batch = create_batch(db_session, auditor, BatchType.AUDIT, "Rack A", "")
    add_serial_to_batch(db_session, batch, auditor, in_stock[0].serial_number)
    add_serial_to_batch(db_session, batch, auditor, sold.serial_number)
    summary = reconcile_audit_batch(db_session, batch)
    assert summary.verified == 1
    assert summary.missing == 1
    assert summary.extra == 1
    findings = {finding.finding_type for finding in batch.audit_findings}
    assert findings == {"VERIFIED", "MISSING", "EXTRA"}


def test_audit_submit_logs_audit_transaction(db_session):
    auditor = User(username="auditor2", password_hash="x", role="auditor")
    product = Product(
        product_code="SG041",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    location = StorageLocation(
        code="AUDIT-SHELF",
        warehouse="MAIN",
        zone="A",
        section="1",
        rack="R1",
        shelf="S1",
        bin="B1",
    )
    db_session.add_all([auditor, product, location])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, auditor, BatchType.AUDIT, "Rack A", "")
    add_serial_to_batch(db_session, batch, auditor, serial.serial_number)
    verify_pending_items_on_shelf(db_session, batch=batch, location=location, user=auditor)
    apply_batch_statuses(db_session, batch, auditor)
    txn = db_session.scalar(select(InventoryTransaction).where(InventoryTransaction.serial_id == serial.id))
    assert txn.transaction_type == TransactionType.AUDIT.value
    assert txn.status_from == SerialStatus.IN_STOCK.value
    assert txn.status_to == SerialStatus.IN_STOCK.value
