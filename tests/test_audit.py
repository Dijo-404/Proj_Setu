from app.models import BatchType, Product, SerialStatus, User
from app.services.audit import reconcile_audit_batch
from app.services.inventory import add_serial_to_batch, create_batch, generate_serials


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
