from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Company, User
from app.security import create_session_token
from app.services.settings import add_company, get_all_settings


COMPANY_CONFIG = {
    "company_name": "Original Tally Company",
    "tally_host": "127.0.0.1",
    "tally_port": "9000",
    "sales_voucher_type": "Sales",
    "purchase_voucher_type": "Purchase",
    "sales_ledger_name": "Sales Ledger",
    "purchase_ledger_name": "Purchase Ledger",
    "cgst_ledger_name": "CGST Ledger",
    "sgst_ledger_name": "SGST Ledger",
    "sales_gst_ledger_mappings": "",
    "round_off_ledger_name": "Round Off",
}


def test_tally_check_lists_company_names_and_updates_from_modal_endpoint():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(
            User(
                id=1,
                username="company-admin",
                password_hash="x",
                role="admin",
                active=True,
            )
        )
        db.commit()
        company = add_company(db, "Original Label", COMPANY_CONFIG)
        company_id = company.id

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        cookies = {SESSION_COOKIE: create_session_token(1)}
        page = client.get("/tally-check", cookies=cookies)
        update = client.post(
            f"/tally-check/companies/{company_id}",
            cookies=cookies,
            headers={"Accept": "application/json"},
            data={
                **COMPANY_CONFIG,
                "name": "Edited Label",
                "company_name": "Edited Tally Company",
                "sales_ledger_name": "Sales @ 5%",
            },
        )
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        saved_company = db.get(Company, company_id)
        settings = get_all_settings(db)
        saved_name = saved_company.name
        saved_tally_name = saved_company.tally_company_name
    engine.dispose()

    assert page.status_code == 200
    assert 'data-company-open="company-modal-' in page.text
    assert "Original Label" in page.text
    assert "Required Tally masters" not in page.text
    assert 'name="default_party_name"' not in page.text
    assert update.status_code == 200
    assert update.json()["ok"]
    assert saved_name == "Edited Label"
    assert saved_tally_name == "Edited Tally Company"
    assert settings["sales_ledger_name"] == "Sales @ 5%"
