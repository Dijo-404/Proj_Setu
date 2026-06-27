from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from app.models import BatchType, Product, SerialStatus, StorageLocation, User
from app.services import tally as tally_service
from app.services.inventory import apply_batch_statuses, add_serial_to_batch, create_batch, generate_serials
from app.services.shelf_verification import verify_pending_items_on_shelf
from app.services.tally import TallySyncError, build_voucher_xml, post_to_tally


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_post_to_tally_treats_zero_created_as_failure(monkeypatch):
    body = "<RESPONSE><CREATED>0</CREATED><ALTERED>0</ALTERED><EXCEPTIONS>1</EXCEPTIONS></RESPONSE>"
    monkeypatch.setattr(tally_service, "urlopen", lambda *a, **k: _FakeResponse(body))
    with pytest.raises(TallySyncError) as err:
        post_to_tally("<xml/>", {"tally_host": "localhost", "tally_port": "9000"})
    assert not err.value.retryable
    assert "created/altered nothing" in str(err.value).lower()


def test_post_to_tally_accepts_created_voucher(monkeypatch):
    body = "<RESPONSE><CREATED>1</CREATED><ALTERED>0</ALTERED></RESPONSE>"
    monkeypatch.setattr(tally_service, "urlopen", lambda *a, **k: _FakeResponse(body))
    result = post_to_tally("<xml/>", {"tally_host": "localhost", "tally_port": "9000"})
    assert result.reference == "CREATED=1; ALTERED=0"


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
    assert "<AMOUNT>450.00</AMOUNT>" in xml


def _accounting_sum(xml: str) -> Decimal:
    root = ET.fromstring(xml)
    total = Decimal("0")
    for container in root.iter():
        if container.tag in {"LEDGERENTRIES.LIST", "ACCOUNTINGALLOCATIONS.LIST"}:
            amount = container.findtext("AMOUNT")
            if amount is not None:
                total += Decimal(amount)
    return total


def test_sale_voucher_xml_is_balanced_with_tax_and_party(db_session):
    user = User(username="sales-bal", password_hash="x", role="sales")
    product = Product(
        product_code="SG005",
        product_name="Masala",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=500,
        tally_stock_item_name="Masala",
    )
    db_session.add_all([user, product])
    db_session.commit()
    serial = generate_serials(db_session, product, 1, initial_status=SerialStatus.IN_STOCK)[0]
    batch = create_batch(db_session, user, BatchType.SALE, "SANGEETHA", "")
    add_serial_to_batch(db_session, batch, user, serial.serial_number)
    apply_batch_statuses(db_session, batch, user)

    xml = build_voucher_xml(batch, VALID_SETTINGS)

    assert VALID_SETTINGS["cgst_ledger_name"] in xml
    assert VALID_SETTINGS["sgst_ledger_name"] in xml
    assert "SANGEETHA" in xml
    assert "<AMOUNT>-525.00</AMOUNT>" in xml
    assert _accounting_sum(xml) == Decimal("0.00")


def test_purchase_voucher_xml_is_balanced(db_session):
    user = User(username="purch-bal", password_hash="x", role="purchase")
    product = Product(
        product_code="SG006",
        product_name="Masala",
        hsn="0910",
        gst_rate=18,
        unit="Pcs",
        default_rate=333,
        tally_stock_item_name="Masala",
    )
    location = StorageLocation(
        code="TALLY-PURCHASE-SHELF",
        warehouse="MAIN",
        zone="A",
        section="1",
        rack="R1",
        shelf="S1",
        bin="B1",
    )
    db_session.add_all([user, product, location])
    db_session.commit()
    serials = generate_serials(db_session, product, 3)
    batch = create_batch(db_session, user, BatchType.PURCHASE, "Vendor", "")
    for serial in serials:
        add_serial_to_batch(db_session, batch, user, serial.serial_number)
    verify_pending_items_on_shelf(db_session, batch=batch, location=location, user=user)
    apply_batch_statuses(db_session, batch, user)

    xml = build_voucher_xml(batch, VALID_SETTINGS)

    assert _accounting_sum(xml) == Decimal("0.00")
