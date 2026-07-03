from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.models import BatchItem, BatchType, Product, ScanLog, SerialStatus, User
from app.services.assignment import parse_bulk_assignment_xlsx
from app.services.inventory import InventoryError, add_serial_to_batch, create_batch, generate_serials
from app.services.sale_returns import scan_sale_return_product
from app.services.tally_excel import batch_tally_xlsx, import_tally_excel_to_batch


def _workbook_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _product(code: str = "TALLYXL") -> Product:
    return Product(
        product_code=code,
        product_name="Tally Excel Product",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Tally Excel Product",
    )


def test_tally_excel_import_picks_fefo_stock_and_keeps_rate(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = _product()
    db_session.add_all([user, product])
    db_session.commit()
    late = generate_serials(
        db_session,
        product,
        1,
        initial_status=SerialStatus.IN_STOCK,
        expiry_date=date(2026, 12, 31),
    )[0]
    early = generate_serials(
        db_session,
        product,
        1,
        initial_status=SerialStatus.IN_STOCK,
        expiry_date=date(2026, 8, 1),
    )[0]
    next_early = generate_serials(
        db_session,
        product,
        1,
        initial_status=SerialStatus.IN_STOCK,
        expiry_date=date(2026, 9, 1),
    )[0]
    batch = create_batch(db_session, user, BatchType.ISSUE, "Marketing", "", "SAMPLE")
    data = _workbook_bytes(
        ["Description of Goods", "Quantity", "Rate"],
        [[product.tally_stock_item_name, 2, 123.45]],
    )

    result = import_tally_excel_to_batch(db_session, batch, user, data)

    items = db_session.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id)).all()
    logs = db_session.scalars(select(ScanLog).where(ScanLog.batch_id == batch.id)).all()
    assert result.quantity == 2
    assert {item.serial_id for item in items} == {early.id, next_early.id}
    assert late.id not in {item.serial_id for item in items}
    assert {item.rate for item in items} == {123.45}
    assert all(item.fefo_picked for item in items)
    assert {log.status for log in logs} == {"EXCEL_IMPORTED"}


def test_tally_excel_export_can_be_read_back_as_import_lines(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = _product("TALLYX2")
    db_session.add_all([user, product])
    db_session.commit()
    generate_serials(db_session, product, 2, initial_status=SerialStatus.IN_STOCK)
    batch = create_batch(db_session, user, BatchType.ISSUE, "Marketing", "", "SAMPLE")
    import_tally_excel_to_batch(
        db_session,
        batch,
        user,
        _workbook_bytes(["Product Code", "Quantity", "Rate"], [[product.product_code, 2, 88.5]]),
    )

    data = batch_tally_xlsx(batch)
    workbook = load_workbook(BytesIO(data), data_only=True)
    sheet = workbook.active
    lines = parse_bulk_assignment_xlsx(db_session, data, allow_product_create=False)

    assert data.startswith(b"PK")
    assert sheet["B6"].value == "Description of Goods"
    assert sheet["B7"].value == product.tally_stock_item_name
    assert sheet["F7"].value == 2
    assert sheet["H7"].value == 88.5
    assert len(lines) == 1
    assert lines[0].product.id == product.id
    assert lines[0].quantity == 2
    assert lines[0].rate == Decimal("88.5")


def test_tally_excel_import_rejects_purchase_batches(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = _product("TALLYX3")
    db_session.add_all([user, product])
    db_session.commit()
    batch = create_batch(db_session, user, BatchType.PURCHASE, "Supplier", "")
    data = _workbook_bytes(["Product Code", "Quantity"], [[product.product_code, 1]])

    with pytest.raises(InventoryError, match="sale, issue, and purchase return"):
        import_tally_excel_to_batch(db_session, batch, user, data)


def test_sale_tally_excel_import_waits_for_pending_return_shelf_scan(db_session):
    user = User(username="sales", password_hash="x", role="sales")
    product = _product("TALLYX4")
    db_session.add_all([user, product])
    db_session.commit()
    serials = generate_serials(db_session, product, 2, initial_status=SerialStatus.IN_STOCK)
    batch = create_batch(db_session, user, BatchType.SALE, "Customer Ledger", "")
    add_serial_to_batch(db_session, batch, user, serials[0].serial_number)
    scan_sale_return_product(db_session, batch, user, serials[0].serial_number)
    data = _workbook_bytes(["Product Code", "Quantity"], [[product.product_code, 1]])

    with pytest.raises(InventoryError, match="shelf QR"):
        import_tally_excel_to_batch(db_session, batch, user, data)

    items = db_session.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id)).all()
    assert items == []
