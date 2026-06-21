from app.models import BatchType, Product, SerialStatus, User
from app.services.inventory import apply_batch_statuses, add_serial_to_batch, create_batch, generate_serials
from app.services.settings import DEFAULT_SETTINGS
from app.services.tally import build_voucher_xml


def test_sale_batch_xml_groups_serials_by_product(db_session):
    user = User(username="sales", password_hash="x", role="sales")
    product = Product(
        product_code="SG003",
        product_name="Biryani Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=500,
        tally_stock_item_name="Sg Biriyani Masala 100grm",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serials = generate_serials(db_session, product, 2, initial_status=SerialStatus.IN_STOCK)
    batch = create_batch(db_session, user, BatchType.SALE, "SANGEETHA", "")
    for serial in serials:
        add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)
    xml = build_voucher_xml(batch, DEFAULT_SETTINGS)
    assert xml.count("<ALLINVENTORYENTRIES.LIST>") == 1
    assert "2 Pcs" in xml
    assert "Sg Biriyani Masala 100grm" in xml
