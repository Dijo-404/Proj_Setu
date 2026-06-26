from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Product, Serial, SerialStatus, User
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


def test_super_admin_can_delete_unused_product_and_name_edit_is_removed():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(User(id=1, username="root", password_hash="x", role="super_admin", active=True))
        db.add(
            Product(
                product_code="DEL",
                product_name="Delete Me",
                hsn="0910",
                gst_rate=5,
                unit="Pcs",
                tally_stock_item_name="Delete Me",
            )
        )
        db.commit()
        product_id = db.scalar(select(Product.id).where(Product.product_code == "DEL"))

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
        legacy_get = client.get(f"/products/{product_id}/name", cookies=cookies)
        legacy_post = client.post(f"/products/{product_id}/name", data={"product_name": "Renamed"}, cookies=cookies)
        with Session() as db:
            product_name = db.scalar(select(Product.product_name).where(Product.id == product_id))
        delete = client.post(f"/products/{product_id}/delete", cookies=cookies)
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        deleted = db.scalar(select(Product).where(Product.product_code == "DEL"))
    engine.dispose()

    assert page.status_code == 200
    assert f"/products/{product_id}/name" not in page.text
    assert f"/products/{product_id}/delete" in page.text
    assert legacy_get.status_code == 303
    assert legacy_get.headers["location"] == "/products"
    assert legacy_post.status_code == 303
    assert legacy_post.headers["location"] == "/products"
    assert product_name == "Delete Me"
    assert delete.status_code == 303
    assert deleted is None


def test_product_delete_requires_super_admin_and_blocks_used_product():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(User(id=1, username="admin", password_hash="x", role="admin", active=True))
        db.add(User(id=2, username="root", password_hash="x", role="super_admin", active=True))
        product = Product(
            product_code="USED",
            product_name="Used Product",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            tally_stock_item_name="Used Product",
        )
        db.add(product)
        db.commit()
        db.add(Serial(serial_number="USED-000001", product_id=product.id, status=SerialStatus.GENERATED.value))
        db.commit()
        product_id = product.id

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        admin_delete = client.post(f"/products/{product_id}/delete", cookies={SESSION_COOKIE: create_session_token(1)})
        super_delete = client.post(f"/products/{product_id}/delete", cookies={SESSION_COOKIE: create_session_token(2)})
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        still_exists = db.scalar(select(Product).where(Product.product_code == "USED"))
    engine.dispose()

    assert admin_delete.status_code == 403
    assert super_delete.status_code == 303
    assert super_delete.headers["location"] == "/products?error=product_delete_blocked"
    assert still_exists is not None
