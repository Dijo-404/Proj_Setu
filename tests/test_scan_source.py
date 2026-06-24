from app.models import Role, User
from app.routers.batches import can_use_manual_scan, scan_source_allowed


def test_admin_roles_can_use_manual_scan_source():
    admin = User(username="admin", password_hash="x", role=Role.ADMIN.value)
    super_admin = User(username="root", password_hash="x", role=Role.SUPER_ADMIN.value)

    assert can_use_manual_scan(admin)
    assert can_use_manual_scan(super_admin)
    assert scan_source_allowed(admin, "manual")
    assert scan_source_allowed(super_admin, "manual")


def test_staff_roles_must_use_camera_scan_source():
    purchase = User(username="purchase", password_hash="x", role=Role.PURCHASE.value)
    sales = User(username="sales", password_hash="x", role=Role.SALES.value)
    auditor = User(username="auditor", password_hash="x", role=Role.AUDITOR.value)

    for user in [purchase, sales, auditor]:
        assert not can_use_manual_scan(user)
        assert scan_source_allowed(user, "camera")
        assert not scan_source_allowed(user, "manual")
