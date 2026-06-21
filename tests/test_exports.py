from app.models import BatchType, Product, ScanLog, SerialStatus, User
from app.services.audit import reconcile_audit_batch
from app.services.exports import audit_report_pdf, qr_labels_pdf, scans_xlsx
from app.services.inventory import add_serial_to_batch, create_batch, generate_serials


def test_scans_xlsx_generates_workbook(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    db_session.add(user)
    db_session.commit()
    scan = ScanLog(serial_number_raw="SG001-000001", user_id=user.id, action="AUDIT", status="SCANNED")
    db_session.add(scan)
    db_session.commit()
    data = scans_xlsx([scan])
    assert data.startswith(b"PK")


def test_qr_labels_pdf_generates_pdf(db_session):
    product = Product(
        product_code="SG050",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add(product)
    db_session.commit()
    serial = generate_serials(db_session, product, 1)[0]
    data = qr_labels_pdf([serial])
    assert data.startswith(b"%PDF")


def test_audit_report_pdf_generates_pdf(db_session):
    auditor = User(username="auditor", password_hash="x", role="auditor")
    product = Product(
        product_code="SG051",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([auditor, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, auditor, BatchType.AUDIT, "Rack A", "")
    add_serial_to_batch(db_session, batch, auditor, serial.serial_number)
    reconcile_audit_batch(db_session, batch)
    data = audit_report_pdf(batch)
    assert data.startswith(b"%PDF")
