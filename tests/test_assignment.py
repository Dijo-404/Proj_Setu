from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select

from app.models import BatchStatus, BatchType, InventoryTransaction, Product, SerialStatus, TransactionType, User
from app.services.assignment import AssignmentLine, assign_barcodes_to_existing_stock, parse_bulk_assignment_xlsx
from app.services.exports import serials_xlsx


def make_product(code="SG080"):
    return Product(
        product_code=code,
        product_name="Turmeric Powder 100g",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="SG Turmeric Powder 100g",
    )


def test_assign_barcodes_to_existing_stock_creates_history(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = make_product()
    db_session.add_all([user, product])
    db_session.commit()

    batch = assign_barcodes_to_existing_stock(db_session, user, [AssignmentLine(product=product, quantity=3)])

    assert batch.batch_type == BatchType.QR_ASSIGNMENT.value
    assert batch.status == BatchStatus.CLOSED.value
    assert len(batch.items) == 3
    assert {item.serial.status for item in batch.items} == {SerialStatus.IN_STOCK.value}
    transactions = db_session.scalars(select(InventoryTransaction).order_by(InventoryTransaction.id)).all()
    assert [txn.transaction_type for txn in transactions] == [TransactionType.QR_ASSIGNMENT.value] * 3
    assert {txn.status_to for txn in transactions} == {SerialStatus.IN_STOCK.value}


def test_bulk_assignment_xlsx_uses_existing_product_codes(db_session):
    product = make_product("SG081")
    db_session.add(product)
    db_session.commit()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Product Code", "Quantity"])
    sheet.append(["SG081", 2])
    stream = BytesIO()
    workbook.save(stream)

    lines = parse_bulk_assignment_xlsx(db_session, stream.getvalue())

    assert len(lines) == 1
    assert lines[0].product.id == product.id
    assert lines[0].quantity == 2


def test_serials_xlsx_exports_generated_barcodes(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = make_product("SG082")
    db_session.add_all([user, product])
    db_session.commit()
    batch = assign_barcodes_to_existing_stock(db_session, user, [AssignmentLine(product=product, quantity=1)])

    data = serials_xlsx([batch.items[0].serial])

    assert data.startswith(b"PK")
