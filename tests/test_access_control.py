from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_session_token
from app.services.access_control import ROLE_COLUMNS, config_from_form, get_role_access_config, landing_path_for, role_access_sections, save_role_access_config


def test_role_access_catalog_has_cells_for_every_role():
    role_count = len(ROLE_COLUMNS)
    sections = role_access_sections()

    assert [section.title for section in sections] == [
        "Pages shown in navigation",
        "Actions allowed by role",
        "Data access and modification",
    ]
    assert all(len(row.cells) == role_count for section in sections for row in section.rows)


def test_directors_default_access_is_reports_only():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        config = get_role_access_config(db)

    engine.dispose()

    assert config["page_reports"]["directors"] == "shown"
    assert config["reports_data"]["directors"] == "view"
    assert config["page_dashboard"]["directors"] == "hidden"
    assert config["dashboard_data"]["directors"] == "no"
    assert config["batch_list"]["directors"] == "no"
    assert config["product_master"]["directors"] == "no"
    assert config["serial_data"]["directors"] == "no"
    assert config["reports_export"]["directors"] == "no"
    assert landing_path_for(config, "directors") == "/reports"


def test_role_access_partial_save_merges_existing_values_and_ignores_bad_keys():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        save_role_access_config(db, {"reports_data": {"admin": "no", "purchase": "view"}})
        submitted = config_from_form(
            [
                ("access__reports_data__admin", "view"),
                ("access__reports_data__purchase", "invalid"),
                ("access__bad", "edit"),
            ]
        )
        save_role_access_config(db, submitted)
        saved = get_role_access_config(db)

    engine.dispose()

    assert saved["reports_data"]["admin"] == "view"
    assert saved["reports_data"]["purchase"] == "view"


def test_role_access_page_is_super_admin_only():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add_all(
            [
                User(id=1, username="admin", password_hash="x", role="admin", active=True),
                User(id=2, username="purchase", password_hash="x", role="purchase", active=True),
                User(id=3, username="root", password_hash="x", role="super_admin", active=True),
            ]
        )
        db.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        root_response = client.get("/settings/access", cookies={SESSION_COOKIE: create_session_token(3)})
        admin_response = client.get("/settings/access", cookies={SESSION_COOKIE: create_session_token(1)})
        purchase_response = client.get("/settings/access", cookies={SESSION_COOKIE: create_session_token(2)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert root_response.status_code == 200
    assert "Role Access" in root_response.text
    assert "Manual serial entry" in root_response.text
    assert "access-matrix-scroll--limited" in root_response.text
    assert 'class="table-scroll"' not in root_response.text
    assert 'href="/settings/access">Role access</a>' in root_response.text
    assert 'name="access__page_reports__admin"' in root_response.text
    assert ">Purchase</summary>" in root_response.text
    assert ">Sales</summary>" in root_response.text
    assert ">Stock</summary>" in root_response.text
    assert ">Batches</summary>" not in root_response.text
    workflow_markers = [
        ">Dashboard</a>",
        ">Purchase</summary>",
        ">Sales</summary>",
        ">Stock</summary>",
        ">Warehouse</summary>",
        ">Barcodes</summary>",
        ">Serials</a>",
        ">Reports</a>",
        ">Tally Check</a>",
        ">Admin</summary>",
    ]
    assert [root_response.text.index(marker) for marker in workflow_markers] == sorted(
        root_response.text.index(marker) for marker in workflow_markers
    )
    assert admin_response.status_code == 403
    assert purchase_response.status_code == 403


def test_super_admin_can_change_role_access_and_route_uses_saved_permission():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add_all(
            [
                User(id=1, username="admin", password_hash="x", role="admin", active=True),
                User(id=2, username="root", password_hash="x", role="super_admin", active=True),
            ]
        )
        db.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        admin_cookies = {SESSION_COOKIE: create_session_token(1)}
        root_cookies = {SESSION_COOKIE: create_session_token(2)}
        allowed_response = client.get("/reports", cookies=admin_cookies)
        save_response = client.post(
            "/settings/access",
            data={
                "access__page_reports__admin": "hidden",
                "access__reports_data__admin": "no",
            },
            cookies=root_cookies,
        )
        blocked_response = client.get("/reports", cookies=admin_cookies)
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        saved = get_role_access_config(db)
    engine.dispose()

    assert allowed_response.status_code == 200
    assert save_response.status_code == 303
    assert blocked_response.status_code == 403
    assert saved["page_reports"]["admin"] == "hidden"
    assert saved["reports_data"]["admin"] == "no"


def test_label_file_view_access_cannot_mark_labels_printed():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(User(id=2, username="purchase", password_hash="x", role="purchase", active=True))
        db.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        cookies = {SESSION_COOKIE: create_session_token(2)}
        preview_response = client.get("/serials/labels", cookies=cookies)
        print_response = client.post("/serials/labels/print", json={"ids": []}, cookies=cookies)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert preview_response.status_code == 200
    assert "cannot print labels" in preview_response.text
    assert print_response.status_code == 403


def test_hidden_pages_and_actions_appear_after_super_admin_grants_access():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add_all(
            [
                User(id=1, username="admin", password_hash="x", role="admin", active=True),
                User(id=2, username="root", password_hash="x", role="super_admin", active=True),
            ]
        )
        save_role_access_config(
            db,
            {
                "page_reports": {"admin": "hidden"},
                "batch_purchase": {"admin": "no"},
                "product_create": {"admin": "no"},
                "reports_export": {"admin": "no"},
                "backup_download": {"admin": "no"},
            },
        )

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        admin_cookies = {SESSION_COOKIE: create_session_token(1)}
        root_cookies = {SESSION_COOKIE: create_session_token(2)}

        dashboard_before = client.get("/", cookies=admin_cookies)
        products_before = client.get("/products", cookies=admin_cookies)
        reports_before = client.get("/reports", cookies=admin_cookies)
        maintenance_before = client.get("/maintenance", cookies=admin_cookies)

        grant = client.post(
            "/settings/access",
            cookies=root_cookies,
            data={
                "access__page_reports__admin": "shown",
                "access__batch_purchase__admin": "edit",
                "access__product_create__admin": "edit",
                "access__reports_export__admin": "yes",
                "access__backup_download__admin": "yes",
            },
        )

        dashboard_after = client.get("/", cookies=admin_cookies)
        products_after = client.get("/products", cookies=admin_cookies)
        reports_after = client.get("/reports", cookies=admin_cookies)
        maintenance_after = client.get("/maintenance", cookies=admin_cookies)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert 'href="/reports"' not in dashboard_before.text
    assert 'href="/batches/new?batch_type=PURCHASE"' not in dashboard_before.text
    assert "New product" not in products_before.text
    assert "Transactions CSV" not in reports_before.text
    assert "Download backup" not in maintenance_before.text

    assert grant.status_code == 303
    assert 'href="/reports"' in dashboard_after.text
    assert 'href="/batches/new?batch_type=PURCHASE"' in dashboard_after.text
    assert "New product" in products_after.text
    assert "Transactions CSV" in reports_after.text
    assert "Download backup" in maintenance_after.text
