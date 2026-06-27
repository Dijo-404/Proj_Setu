from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


def _client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, follow_redirects=False), engine


def test_cross_origin_post_is_blocked():
    client, engine = _client()
    try:
        response = client.post(
            "/login",
            data={"username": "admin", "password": "x"},
            headers={"Origin": "http://evil.example"},
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code == 403
    assert "CSRF" in response.text


def test_same_origin_post_passes_csrf_check():
    client, engine = _client()
    try:
        response = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            headers={"Origin": "http://testserver"},
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code != 403


def test_get_is_not_blocked():
    client, engine = _client()
    try:
        response = client.get("/login", headers={"Origin": "http://evil.example"})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
    assert response.status_code == 200
