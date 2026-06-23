from io import BytesIO

from PIL import Image

from app.models import BatchType, Product, ScanLog, SerialStatus, User
from app.services.audit import reconcile_audit_batch
from app.services.exports import audit_report_pdf, barcode_labels_pdf, barcode_png, scans_xlsx
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


def test_barcode_png_is_a_wide_1d_barcode():
    data = barcode_png("RCV-20260623-0001")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = Image.open(BytesIO(data)).size
    # Code128 is a horizontal 1D barcode: clearly wider than tall.
    # A square (≈1:1) image would mean we are still emitting a QR code.
    assert width > height * 1.5


def _make_product(db_session, code: str) -> Product:
    product = Product(
        product_code=code,
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_barcode_labels_pdf_generates_pdf(db_session):
    product = _make_product(db_session, "SG050")
    serial = generate_serials(db_session, product, 1)[0]
    data = barcode_labels_pdf([serial])
    assert data.startswith(b"%PDF")


def test_audit_report_pdf_generates_pdf(db_session):
    auditor = User(username="auditor", password_hash="x", role="auditor")
    product = _make_product(db_session, "SG051")
    db_session.add(auditor)
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, auditor, BatchType.AUDIT, "Rack A", "")
    add_serial_to_batch(db_session, batch, auditor, serial.serial_number)
    reconcile_audit_batch(db_session, batch)
    data = audit_report_pdf(batch)
    assert data.startswith(b"%PDF")
