from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Product, User
from app.security import create_session_token


def test_product_master_saves_and_updates_sales_discount_rate():
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
        page = client.get("/products", cookies=cookies)
        create = client.post(
            "/products",
            data={
                "product_code": "D001",
                "product_name": "Discount Item",
                "category": "",
                "hsn": "0910",
                "gst_rate": "5",
                "unit": "Pcs",
                "default_rate": "500",
                "sales_discount_rate": "7.5",
                "tally_stock_item_name": "Discount Item",
            },
            cookies=cookies,
        )
        with Session() as db:
            product = db.scalar(select(Product).where(Product.product_code == "D001"))
            product_id = product.id
        update = client.post(
            f"/products/{product_id}/pricing",
            data={"default_rate": "525", "sales_discount_rate": "12"},
            cookies=cookies,
        )
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        saved = db.scalar(select(Product).where(Product.product_code == "D001"))
        assert saved.default_rate == 525
        assert saved.sales_discount_rate == 12
    engine.dispose()

    assert page.status_code == 200
    assert "Sales discount %" in page.text
    assert create.status_code == 303
    assert update.status_code == 303
