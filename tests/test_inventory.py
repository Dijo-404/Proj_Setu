from app.models import BatchType, Product, SerialStatus, User
from app.services.inventory import InventoryError, add_serial_to_batch, create_batch, generate_serials


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
