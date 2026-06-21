from app.models import Product, SerialStatus, User
from app.services.inventory import InventoryError, generate_serials
from app.services.replacement import replace_qr_serial


def test_replace_qr_serial_links_old_and_new(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = Product(
        product_code="SG070",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    old = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    replacement = replace_qr_serial(db_session, user, old.serial_number, None, "Damaged label")
    db_session.refresh(old)
    assert old.status == SerialStatus.REPLACED.value
    assert not old.active
    assert old.replaced_by_id == replacement.id
    assert replacement.status == SerialStatus.IN_STOCK.value


def test_replace_qr_serial_rejects_replaced_serial(db_session):
    user = User(username="admin", password_hash="x", role="admin")
    product = Product(
        product_code="SG071",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    old = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    replace_qr_serial(db_session, user, old.serial_number)
    try:
        replace_qr_serial(db_session, user, old.serial_number)
    except InventoryError as exc:
        assert "already" in str(exc)
    else:
        assert False
