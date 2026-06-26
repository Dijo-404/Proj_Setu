from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Batch, BatchType, User
from app.security import create_session_token


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def test_super_admin_can_delete_unused_user():
    engine, Session = make_session()
    with Session() as db:
        db.add(User(id=1, username="root", password_hash="x", role="super_admin", active=True))
        db.add(User(id=2, username="temp", password_hash="x", role="purchase", active=False))
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
        page = client.get("/users", cookies=cookies)
        delete = client.post("/users/2/delete", cookies=cookies)
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        deleted = db.get(User, 2)
    engine.dispose()

    assert page.status_code == 200
    assert 'action="/users/2/delete"' in page.text
    assert 'action="/users/1/delete"' not in page.text
    assert delete.status_code == 303
    assert delete.headers["location"] == "/users"
    assert deleted is None


def test_user_delete_is_super_admin_only_and_archives_history_user():
    engine, Session = make_session()
    with Session() as db:
        db.add(User(id=1, username="admin", password_hash="x", role="admin", active=True))
        db.add(User(id=2, username="root", password_hash="x", role="super_admin", active=True))
        db.add(User(id=3, username="used", password_hash="x", role="sales", active=False))
        db.add(Batch(batch_number="B-1", batch_type=BatchType.SALE.value, user_id=3))
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
        admin_page = client.get("/users", cookies={SESSION_COOKIE: create_session_token(1)})
        admin_delete = client.post("/users/3/delete", cookies={SESSION_COOKIE: create_session_token(1)})
        self_delete = client.post("/users/2/delete", cookies={SESSION_COOKIE: create_session_token(2)})
        used_delete = client.post("/users/3/delete", cookies={SESSION_COOKIE: create_session_token(2)})
        after_delete_page = client.get("/users", cookies={SESSION_COOKIE: create_session_token(2)})
        deleted_session_page = client.get("/users", cookies={SESSION_COOKIE: create_session_token(3)})
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        used = db.scalar(select(User).where(User.username == "used"))
        root = db.scalar(select(User).where(User.username == "root"))
    engine.dispose()

    assert admin_page.status_code == 200
    assert "Delete user" not in admin_page.text
    assert admin_delete.status_code == 403
    assert self_delete.status_code == 303
    assert self_delete.headers["location"] == "/users?error=user_delete_self"
    assert used_delete.status_code == 303
    assert used_delete.headers["location"] == "/users"
    assert "used" not in after_delete_page.text
    assert deleted_session_page.status_code == 303
    assert deleted_session_page.headers["location"] == "/login"
    assert used is not None
    assert used.active is False
    assert used.deleted_at is not None
    assert root is not None
