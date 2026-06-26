from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_session_token, hash_password, verify_password
from app.services.bootstrap import bootstrap


def test_bootstrap_default_admin_must_change_password(db_session):
    bootstrap(db_session)
    admin = db_session.query(User).filter(User.username == "admin").one()
    assert admin.must_change_password is True


def _client_with_user(must_change=True):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(
            User(
                id=1,
                username="admin",
                password_hash=hash_password("admin123"),
                role="super_admin",
                active=True,
                must_change_password=must_change,
            )
        )
        db.commit()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, follow_redirects=False), Session, engine


def test_must_change_password_gate_redirects_protected_route():
    client, Session, engine = _client_with_user(must_change=True)
    try:
        response = client.get("/", cookies={SESSION_COOKIE: create_session_token(1)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code == 303
    assert response.headers["location"] == "/account/password"


def test_change_password_clears_flag_and_updates_hash():
    client, Session, engine = _client_with_user(must_change=True)
    try:
        response = client.post(
            "/account/password",
            data={
                "current_password": "admin123",
                "new_password": "a-strong-new-pass",
                "confirm_password": "a-strong-new-pass",
            },
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
        with Session() as db:
            user = db.get(User, 1)
            assert user.must_change_password is False
            assert verify_password("a-strong-new-pass", user.password_hash)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_change_password_rejects_short_password():
    client, Session, engine = _client_with_user(must_change=True)
    try:
        response = client.post(
            "/account/password",
            data={"current_password": "admin123", "new_password": "short", "confirm_password": "short"},
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code == 400
