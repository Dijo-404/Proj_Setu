from app.models import BatchType, Product, SerialStatus, User
from app.services.inventory import apply_batch_statuses, add_serial_to_batch, create_batch, generate_serials
from app.services.tally import build_voucher_xml


VALID_SETTINGS = {
    "company_name": "Setu Test Company",
    "sales_voucher_type": "Sales",
    "purchase_voucher_type": "Purchase",
    "sales_ledger_name": "Sales Ledger",
    "purchase_ledger_name": "Purchase Ledger",
    "cgst_ledger_name": "CGST Ledger",
    "sgst_ledger_name": "SGST Ledger",
    "round_off_ledger_name": "Round Off",
    "default_party_name": "Cash Ledger",
}


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
    xml = build_voucher_xml(batch, VALID_SETTINGS)
    assert xml.count("<ALLINVENTORYENTRIES.LIST>") == 1
    assert "2 Pcs" in xml
    assert "Sg Biriyani Masala 100grm" in xml


def test_sale_batch_xml_includes_sales_discount(db_session):
    user = User(username="sales", password_hash="x", role="sales")
    product = Product(
        product_code="SG004",
        product_name="Biryani Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=500,
        sales_discount_rate=10,
        tally_stock_item_name="Sg Biriyani Masala 100grm",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, user, BatchType.SALE, "SANGEETHA", "")
    add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)

    xml = build_voucher_xml(batch, VALID_SETTINGS)

    assert "<DISCOUNT>10.00</DISCOUNT>" in xml
    assert "<AMOUNT>-450.00</AMOUNT>" in xml
