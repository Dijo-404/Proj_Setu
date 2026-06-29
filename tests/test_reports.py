from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import AuditFinding, Batch, BatchItem, BatchStatus, BatchType, InventoryTransaction, Product, ScanLog, Serial, SerialStatus, TransactionType, User
from app.routers.reports import director_audit_batch_detail, reports as reports_route
from app.security import create_session_token
from app.services.access_control import save_role_access_config
from app.services.expiry import today


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


def test_reports_page_includes_filterable_missing_stock():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        user = User(id=1, username="auditor", password_hash="x", role="admin", active=True)
        product = Product(
            product_code="MISS100",
            product_name="Missing masala",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Missing masala",
        )
        db.add_all([user, product])
        db.flush()
        serial = Serial(
            serial_number="MISS100-000001",
            product_id=product.id,
            status=SerialStatus.IN_STOCK.value,
            product_batch_number="LOT-MISS-01",
            warehouse="Main warehouse",
            mfg_date=today() - timedelta(days=30),
            expiry_date=today() + timedelta(days=120),
        )
        batch = Batch(
            batch_number="AUD-001",
            batch_type=BatchType.AUDIT.value,
            user_id=user.id,
            status=BatchStatus.SUBMITTED.value,
        )
        db.add_all([serial, batch])
        db.flush()
        db.add(
            AuditFinding(
                batch_id=batch.id,
                serial_id=serial.id,
                serial_number=serial.serial_number,
                product_code=product.product_code,
                product_name=product.product_name,
                finding_type="MISSING",
                expected_status=SerialStatus.IN_STOCK.value,
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
        response = client.get(
            "/reports?action=MISSING",
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
        detail_response = client.get(
            "/reports/missing-stock?q=MISS100",
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
        csv_response = client.get(
            "/reports/missing-stock.csv?q=MISS100",
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
        xlsx_response = client.get(
            "/reports/missing-stock.xlsx?q=MISS100",
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    assert '<option value="MISSING" selected>MISSING</option>' in response.text
    assert "<h2>Missing stock</h2>" in response.text
    assert "MISS100-000001" in response.text
    assert "Missing masala" in response.text
    assert "AUD-001" in response.text
    assert "Missing stock CSV" in response.text
    assert "Missing stock XLSX" in response.text

    assert detail_response.status_code == 200
    assert "<h1>Missing stock report</h1>" in detail_response.text
    assert "<h2>Missing stock details</h2>" in detail_response.text
    assert "LOT-MISS-01" in detail_response.text
    assert "Main warehouse" in detail_response.text
    assert "MISS100-000001" in detail_response.text
    assert 'href="/reports/missing-stock"' in detail_response.text
    assert ">Overview</a>" in detail_response.text

    assert csv_response.status_code == 200
    assert "setu-missing-stock.csv" in csv_response.headers["content-disposition"]
    assert "Audit Date,Audited By,Audit Batch,Serial" in csv_response.text
    assert "LOT-MISS-01,Main warehouse" in csv_response.text

    assert xlsx_response.status_code == 200
    assert xlsx_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert xlsx_response.content.startswith(b"PK")


def test_directors_role_gets_report_only_summary_and_audit_detail():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    audit_at = datetime(2026, 6, 28, 10, 30, tzinfo=timezone.utc)
    old_at = datetime.now(timezone.utc) - timedelta(days=140)
    with Session() as db:
        auditor = User(id=1, username="auditor", password_hash="x", role="admin", active=True)
        director = User(id=2, username="director", password_hash="x", role="directors", active=True)
        missing_product = Product(
            product_code="DIR-MISS",
            product_name="Director missing product",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Director missing product",
        )
        risk_product = Product(
            product_code="DIR-RISK",
            product_name="Director expiry risk product",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=80,
            tally_stock_item_name="Director expiry risk product",
        )
        dead_product = Product(
            product_code="DIR-DEAD",
            product_name="Director dead stock product",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=60,
            tally_stock_item_name="Director dead stock product",
            created_at=old_at,
        )
        db.add_all([auditor, director, missing_product, risk_product, dead_product])
        db.flush()
        missing_serial = Serial(
            serial_number="DIR-MISS-001",
            product_id=missing_product.id,
            status=SerialStatus.IN_STOCK.value,
        )
        extra_serial = Serial(
            serial_number="DIR-MISS-EXTRA",
            product_id=missing_product.id,
            status=SerialStatus.SOLD.value,
        )
        risk_serial = Serial(
            serial_number="DIR-RISK-001",
            product_id=risk_product.id,
            status=SerialStatus.IN_STOCK.value,
            product_batch_number="RISK-B1",
            expiry_date=today() + timedelta(days=20),
        )
        dead_serial = Serial(
            serial_number="DIR-DEAD-001",
            product_id=dead_product.id,
            status=SerialStatus.IN_STOCK.value,
        )
        db.add_all([missing_serial, extra_serial, risk_serial, dead_serial])
        db.flush()
        batch = Batch(
            batch_number="AUD-DIR-001",
            batch_type=BatchType.AUDIT.value,
            user_id=auditor.id,
            status=BatchStatus.SUBMITTED.value,
            submitted_at=audit_at,
        )
        db.add(batch)
        db.flush()
        batch_id = batch.id
        db.add_all(
            [
                AuditFinding(
                    batch_id=batch.id,
                    serial_id=missing_serial.id,
                    serial_number=missing_serial.serial_number,
                    product_code=missing_product.product_code,
                    product_name=missing_product.product_name,
                    finding_type="MISSING",
                    expected_status=SerialStatus.IN_STOCK.value,
                ),
                AuditFinding(
                    batch_id=batch.id,
                    serial_id=extra_serial.id,
                    serial_number=extra_serial.serial_number,
                    product_code=missing_product.product_code,
                    product_name=missing_product.product_name,
                    finding_type="EXTRA",
                    expected_status=SerialStatus.IN_STOCK.value,
                    scanned_status=SerialStatus.SOLD.value,
                ),
            ]
        )
        db.commit()

    def signed_request(path: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [(b"cookie", f"{SESSION_COOKIE}={create_session_token(2)}".encode())],
                "query_string": b"",
                "server": ("testserver", 80),
                "scheme": "http",
            }
        )

    with Session() as db:
        report_response = reports_route(signed_request("/reports"), db=db)
        detail_response = director_audit_batch_detail(
            signed_request(f"/reports/audit-batches/{batch_id}"),
            batch_id,
            db=db,
        )
        report_text = report_response.body.decode()
        detail_text = detail_response.body.decode()
    engine.dispose()

    assert report_response.status_code == 200
    assert report_response.template.name == "director_reports.html"
    assert "Directors Report" in report_text
    assert "Reports only" in report_text
    assert "AUD-DIR-001" in report_text
    assert "Missing in last audit" in report_text
    assert "Director expiry risk product" in report_text
    assert "Director dead stock product" in report_text
    assert "Transactions CSV" not in report_text
    assert "<h2>Transactions</h2>" not in report_text
    assert 'href="/reports"' in report_text
    assert ">Dashboard</a>" not in report_text
    assert ">Serials</a>" not in report_text

    assert detail_response.status_code == 200
    assert detail_response.template.name == "director_audit_batch.html"
    assert "Product-wise missing and extra" in detail_text
    assert "Director missing product" in detail_text
    assert "DIR-MISS-001" in detail_text
    assert "DIR-MISS-EXTRA" in detail_text


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
