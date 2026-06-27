from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import Batch, BatchItem, BatchStatus, BatchType, InventoryTransaction, Product, ScanLog, Serial, SerialStatus, TransactionType, User
from app.security import create_session_token
from app.services.access_control import save_role_access_config


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


def test_loss_report_shows_factor_values_for_admin_and_super_admin():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        admin = User(id=1, username="admin", password_hash="x", role="admin", active=True)
        root = User(id=2, username="root", password_hash="x", role="super_admin", active=True)
        sales = User(id=3, username="sales", password_hash="x", role="sales", active=True)
        product = Product(
            product_code="LOSS100",
            product_name="Loss test product",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Loss test product",
        )
        db.add_all([admin, root, sales, product])
        db.flush()
        theft_serial = Serial(
            serial_number="LOSS100-000001",
            product_id=product.id,
            status=SerialStatus.ISSUED.value,
        )
        transport_serial = Serial(
            serial_number="LOSS100-000002",
            product_id=product.id,
            status=SerialStatus.ISSUED.value,
        )
        db.add_all([theft_serial, transport_serial])
        db.flush()
        theft_batch = Batch(
            batch_number="ISS-THEFT-001",
            batch_type=BatchType.ISSUE.value,
            reason_code="THEFT",
            user_id=admin.id,
            status=BatchStatus.SUBMITTED.value,
        )
        transport_batch = Batch(
            batch_number="ISS-TRANSPORT-001",
            batch_type=BatchType.ISSUE.value,
            reason_code="TRANSPORTATION",
            user_id=admin.id,
            status=BatchStatus.SUBMITTED.value,
        )
        db.add_all([theft_batch, transport_batch])
        db.flush()
        db.add_all(
            [
                BatchItem(batch_id=theft_batch.id, serial_id=theft_serial.id, quantity=1, rate=125.50),
                BatchItem(batch_id=transport_batch.id, serial_id=transport_serial.id, quantity=1),
                InventoryTransaction(
                    transaction_type=TransactionType.ISSUE.value,
                    serial_id=theft_serial.id,
                    product_id=product.id,
                    batch_id=theft_batch.id,
                    user_id=admin.id,
                    serial_number=theft_serial.serial_number,
                    status_from=SerialStatus.IN_STOCK.value,
                    status_to=SerialStatus.ISSUED.value,
                    reason_code="THEFT",
                ),
                InventoryTransaction(
                    transaction_type=TransactionType.ISSUE.value,
                    serial_id=transport_serial.id,
                    product_id=product.id,
                    batch_id=transport_batch.id,
                    user_id=admin.id,
                    serial_number=transport_serial.serial_number,
                    status_from=SerialStatus.IN_STOCK.value,
                    status_to=SerialStatus.ISSUED.value,
                    reason_code="TRANSPORTATION",
                ),
            ]
        )
        db.commit()
        save_role_access_config(db, {"reports_data": {"sales": "view"}})

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        admin_response = client.get("/reports", cookies={SESSION_COOKIE: create_session_token(1)})
        root_response = client.get("/reports", cookies={SESSION_COOKIE: create_session_token(2)})
        sales_response = client.get("/reports", cookies={SESSION_COOKIE: create_session_token(3)})
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    for response in (admin_response, root_response):
        assert response.status_code == 200
        assert "<h2>Losses</h2>" in response.text
        assert "<th>Loss due to</th>" in response.text
        assert "Transportation" in response.text
        assert "Theft" in response.text
        assert "Other Things" in response.text
        assert "Rs 125.50" in response.text
        assert "Rs 225.50" in response.text
    assert sales_response.status_code == 200
    assert "<h2>Losses</h2>" not in sales_response.text


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
