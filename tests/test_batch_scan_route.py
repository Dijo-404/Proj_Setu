from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import BatchItem, BatchType, Product, SerialStatus, User
from app.security import create_session_token
from app.services.inventory import create_batch, generate_serials


def test_camera_scan_route_adds_serial_to_batch():
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
            product_code="DIJ",
            product_name="Test Item",
            hsn="0910",
            gst_rate=5,
            unit="Pcs",
            default_rate=100,
            tally_stock_item_name="Test Item",
        )
        db.add_all([user, product])
        db.commit()
        serial = generate_serials(db, product, 1, initial_status=SerialStatus.GENERATED)[0]
        batch = create_batch(db, user, BatchType.PURCHASE, "dijo-test", "")
        serial_number = serial.serial_number
        batch_id = batch.id

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            f"/batches/{batch_id}/scan",
            data={"serial_number": serial_number, "scan_source": "camera"},
            headers={"Accept": "application/json"},
            cookies={SESSION_COOKIE: create_session_token(1)},
        )
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        item = db.scalar(select(BatchItem).where(BatchItem.batch_id == batch_id))
    engine.dispose()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["serial"] == serial_number
    assert item is not None
