from app.models import Product, User
from app.services.tally_masters import (
    build_company_list_xml,
    collect_master_requirements,
    confirm_master,
    confirmation_lookup,
    live_sync_readiness,
    readiness_counts,
)
from app.services.settings import update_settings


VALID_SETTINGS = {
    "company_name": "Setu Test Company",
    "tally_host": "127.0.0.1",
    "tally_port": "9000",
    "sales_voucher_type": "Sales",
    "purchase_voucher_type": "Purchase",
    "sales_ledger_name": "Sales Ledger",
    "purchase_ledger_name": "Purchase Ledger",
    "cgst_ledger_name": "CGST Ledger",
    "sgst_ledger_name": "SGST Ledger",
    "round_off_ledger_name": "Round Off",
    "default_party_name": "Cash Ledger",
}


def test_collect_master_requirements_includes_products_and_settings(db_session):
    update_settings(
        db_session,
        {
            **VALID_SETTINGS,
            "sales_gst_ledger_mappings": (
                "5 | Sales @ 5% | Output CGST @ 2.5% | Output SGST @ 2.5%"
            ),
        },
    )
    product = Product(
        product_code="SG010",
        product_name="Pepper",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=120,
        tally_stock_item_name="Sg Pepper 100grm",
    )
    db_session.add(product)
    db_session.commit()
    requirements = collect_master_requirements(db_session)
    names = {(item.master_type, item.master_name) for item in requirements}
    assert ("Stock Item", "Sg Pepper 100grm") in names
    assert ("Unit", "Pcs") in names
    assert ("Voucher Type", "Sales") in names
    assert ("Ledger", "Sales @ 5%") in names
    assert ("Ledger", "Output CGST @ 2.5%") in names
    assert ("Ledger", "Output SGST @ 2.5%") in names


def test_confirmation_updates_readiness_counts(db_session):
    update_settings(db_session, VALID_SETTINGS)
    user = User(username="admin", password_hash="x", role="admin")
    db_session.add(user)
    db_session.commit()
    requirements = collect_master_requirements(db_session)
    company = next(item for item in requirements if item.master_type == "Company")
    confirm_master(db_session, user, company.master_type, company.master_name, company.source)
    counts = readiness_counts(requirements, confirmation_lookup(db_session))
    assert counts["confirmed"] == 1


def test_company_list_xml_is_read_only_export_request():
    xml = build_company_list_xml()
    assert "<TALLYREQUEST>Export</TALLYREQUEST>" in xml
    assert "<ID>List of Companies</ID>" in xml
    assert "VOUCHER" not in xml


def test_live_sync_readiness_requires_all_confirmations(db_session):
    update_settings(db_session, VALID_SETTINGS)
    user = User(username="admin2", password_hash="x", role="admin")
    db_session.add(user)
    db_session.commit()
    ready, counts = live_sync_readiness(db_session)
    assert not ready
    requirements = collect_master_requirements(db_session)
    for item in requirements:
        confirm_master(db_session, user, item.master_type, item.master_name, item.source)
    ready, counts = live_sync_readiness(db_session)
    assert ready
    assert counts["unchecked"] == 0
