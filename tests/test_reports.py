from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Batch, BatchStatus, BatchType, InventoryTransaction, Product, ScanLog, Serial, SerialStatus, TransactionType, User
from app.security import create_session_token


def test_reports_page_renders_scan_and_transaction_rows():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        user = User(id=1, username="admin", password_hash="x", role="admin", active=True)
        product = Product(
            product_code="SG100",
            product_name="Masala",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Masala",
        )
        db.add_all([user, product])
        db.flush()
        batch = Batch(
            batch_number="BATCH-001",
            batch_type=BatchType.SALE.value,
            user_id=user.id,
            status=BatchStatus.PENDING_SYNC.value,
        )
        db.add(batch)
        db.flush()
        db.add_all(
            [
                InventoryTransaction(
                    transaction_type=TransactionType.SALE.value,
                    product_id=product.id,
                    batch_id=batch.id,
                    user_id=user.id,
                    serial_number="SG100-000001",
                    status_from="IN_STOCK",
                    status_to="SOLD",
                    reference_number=batch.batch_number,
                    tally_reference="TALLY-001",
                ),
                ScanLog(
                    serial_number_raw="SG100-000001",
                    user_id=user.id,
                    action=BatchType.SALE.value,
                    batch_id=batch.id,
                    status="SCANNED",
                ),
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
        response = client.get("/reports", cookies={SESSION_COOKIE: create_session_token(1)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    assert "Transaction mix" in response.text
    assert "Scan outcomes" in response.text
    assert "SG100-000001" in response.text
    assert "TALLY-001" in response.text
    assert "BATCH-001" in response.text


def test_dashboard_renders_stock_and_activity_charts():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        user = User(id=1, username="admin", password_hash="x", role="admin", active=True)
        product = Product(
            product_code="SG200",
            product_name="Pepper",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Pepper",
        )
        db.add_all([user, product])
        db.flush()
        serial = Serial(
            serial_number="SG200-000001",
            product_id=product.id,
            status=SerialStatus.IN_STOCK.value,
        )
        db.add(serial)
        db.flush()
        db.add(
            ScanLog(
                serial_id=serial.id,
                serial_number_raw=serial.serial_number,
                user_id=user.id,
                action=BatchType.AUDIT.value,
                status="SCANNED",
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
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/", cookies={SESSION_COOKIE: create_session_token(1)})
        data_response = client.get("/dashboard/data", cookies={SESSION_COOKIE: create_session_token(1)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    assert "Stock mix" in response.text
    assert "Scan activity" in response.text
    assert "In Stock" in response.text
    assert data_response.status_code == 200
    assert "Stock mix" in data_response.json()["charts_html"]
