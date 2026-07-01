from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import SESSION_COOKIE
from app.database import Base, get_db
from app.main import app
from app.models import BatchItem, BatchType, Product, SerialStatus, StorageLocation, User
from app.security import create_session_token
from app.services.inventory import create_batch, generate_serials


def test_camera_scan_route_adds_multiple_serials_without_restarting():
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
        location = StorageLocation(
            code="SCAN-SHELF",
            warehouse="MAIN",
            zone="A",
            section="1",
            rack="R1",
            shelf="S1",
            bin="B1",
        )
        db.add_all([user, product, location])
        db.commit()
        serials = generate_serials(db, product, 2, initial_status=SerialStatus.GENERATED)
        batch = create_batch(db, user, BatchType.PURCHASE, "dijo-test", "")
        serial_numbers = [serial.serial_number for serial in serials]
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
        responses = []
        shelf_responses = []
        for serial_number in serial_numbers:
            responses.append(client.post(
                f"/batches/{batch_id}/scan",
                data={"serial_number": serial_number, "scan_source": "camera"},
                headers={"Accept": "application/json"},
                cookies={SESSION_COOKIE: create_session_token(1)},
            ))
            shelf_responses.append(client.post(
                f"/batches/{batch_id}/scan",
                data={"serial_number": "SCAN-SHELF", "scan_source": "camera"},
                headers={"Accept": "application/json"},
                cookies={SESSION_COOKIE: create_session_token(1)},
            ))
    finally:
        app.dependency_overrides.clear()

    with Session() as db:
        items = db.scalars(select(BatchItem).where(BatchItem.batch_id == batch_id)).all()
    engine.dispose()

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["ok"] for response in responses] == [True, True]
    assert [response.json()["serial"] for response in responses] == serial_numbers
    assert [response.json()["scan_type"] for response in shelf_responses] == ["shelf", "shelf"]
    assert len(items) == 2
