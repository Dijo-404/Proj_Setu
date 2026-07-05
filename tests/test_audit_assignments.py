from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.auth import SESSION_COOKIE
from app.models import AuditAssignment, Product, SerialStatus, User
from app.routers.audit_assignments import assign_audit, audit_assignments
from app.security import create_session_token
from app.services.inventory import generate_serials


def signed_request(user_id: int, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/audit-assignments",
            "headers": [
                (
                    b"cookie",
                    f"{SESSION_COOKIE}={create_session_token(user_id)}".encode(),
                )
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.mark.parametrize("manager_role", ["admin", "directors"])
def test_admin_and_director_can_assign_timed_product_audit(
    db_session,
    manager_role,
):
    manager = User(
        username=f"{manager_role}-manager",
        password_hash="x",
        role=manager_role,
    )
    auditor = User(username=f"{manager_role}-auditor", password_hash="x", role="auditor")
    product = Product(
        product_code=f"{manager_role[:3].upper()}-AUD",
        product_name=f"{manager_role} audit product",
        hsn="0910",
        gst_rate=5,
        unit="Pcs",
        default_rate=100,
        tally_stock_item_name=f"{manager_role} audit product",
    )
    db_session.add_all([manager, auditor, product])
    db_session.commit()
    generate_serials(
        db_session,
        product,
        2,
        initial_status=SerialStatus.IN_STOCK,
    )
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    response = assign_audit(
        signed_request(manager.id, "POST"),
        product_id=product.id,
        auditor_id=auditor.id,
        starts_at=(now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
        ends_at=(now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        notes="Count this product",
        db=db_session,
    )
    assignment = db_session.scalar(select(AuditAssignment))

    assert response.status_code == 303
    assert assignment.assigned_by_id == manager.id
    assert assignment.auditor_id == auditor.id
    assert len(assignment.expected_items) == 2
    assert len(assignment.batches) == 1
    assert assignment.batches[0].user_id == auditor.id

    auditor_page = audit_assignments(signed_request(auditor.id), db=db_session)
    assert auditor_page.status_code == 200
    assert product.product_name in auditor_page.body.decode()


def test_auditor_cannot_create_assignment(db_session):
    auditor = User(username="self-assign-auditor", password_hash="x", role="auditor")
    db_session.add(auditor)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        assign_audit(
            signed_request(auditor.id, "POST"),
            product_id=1,
            auditor_id=auditor.id,
            starts_at="2026-07-05T09:00",
            ends_at="2026-07-05T17:00",
            db=db_session,
        )

    assert exc_info.value.status_code == 403
