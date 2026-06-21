from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ScanLog, Serial, SerialStatus, User
from app.services.inventory import InventoryError, generate_serials, normalize_serial


def replace_qr_serial(db: Session, user: User, old_serial_number: str, new_serial_number: str | None = None, reason: str | None = None) -> Serial:
    old_serial = db.scalar(select(Serial).where(Serial.serial_number == normalize_serial(old_serial_number)))
    if not old_serial:
        raise InventoryError("Serial number not found")
    if old_serial.status == SerialStatus.REPLACED.value or not old_serial.active:
        raise InventoryError("Serial is already inactive or replaced")

    original_status = SerialStatus(old_serial.status)
    if new_serial_number and new_serial_number.strip():
        replacement = Serial(
            serial_number=normalize_serial(new_serial_number),
            product_id=old_serial.product_id,
            status=original_status.value,
            active=True,
        )
        db.add(replacement)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise InventoryError("Replacement serial already exists") from exc
    else:
        replacement = generate_serials(db, old_serial.product, 1, old_serial.product.product_code, original_status)[0]

    old_serial.status = SerialStatus.REPLACED.value
    old_serial.active = False
    old_serial.replaced_by_id = replacement.id
    db.add(
        ScanLog(
            serial_id=old_serial.id,
            serial_number_raw=old_serial.serial_number,
            user_id=user.id,
            action="QR_REPLACEMENT",
            status="REPLACED",
            message=f"New serial: {replacement.serial_number}. {reason or ''}".strip(),
        )
    )
    db.add(
        ScanLog(
            serial_id=replacement.id,
            serial_number_raw=replacement.serial_number,
            user_id=user.id,
            action="QR_REPLACEMENT",
            status="ACTIVE",
            message=f"Replaces: {old_serial.serial_number}. {reason or ''}".strip(),
        )
    )
    db.commit()
    db.refresh(replacement)
    return replacement
