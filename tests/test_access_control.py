from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_session_token
from app.services.access_control import ROLE_COLUMNS, config_from_form, get_role_access_config, role_access_sections, save_role_access_config


def test_role_access_catalog_has_cells_for_every_role():
    role_count = len(ROLE_COLUMNS)
    sections = role_access_sections()

    assert [section.title for section in sections] == [
        "Pages shown in navigation",
        "Actions allowed by role",
        "Data access and modification",
    ]
    assert all(len(row.cells) == role_count for section in sections for row in section.rows)


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


def test_role_access_page_is_admin_only():
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
        admin_response = client.get("/settings/access", cookies={SESSION_COOKIE: create_session_token(1)})
        purchase_response = client.get("/settings/access", cookies={SESSION_COOKIE: create_session_token(2)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert admin_response.status_code == 200
    assert "Role Access" in admin_response.text
    assert "Manual serial entry" in admin_response.text
    assert "access-matrix-scroll--limited" in admin_response.text
    assert 'class="table-scroll"' not in admin_response.text
    assert 'href="/settings/access">Role access</a>' in admin_response.text
    assert 'name="access__page_reports__admin"' in admin_response.text
    assert purchase_response.status_code == 403


def test_admin_can_change_role_access_and_route_uses_saved_permission():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(User(id=1, username="admin", password_hash="x", role="admin", active=True))
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
        cookies = {SESSION_COOKIE: create_session_token(1)}
        allowed_response = client.get("/reports", cookies=cookies)
        save_response = client.post(
            "/settings/access",
            data={
                "access__page_reports__admin": "hidden",
                "access__reports_data__admin": "no",
            },
            cookies=cookies,
        )
        blocked_response = client.get("/reports", cookies=cookies)
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
