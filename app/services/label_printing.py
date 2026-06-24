from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Serial, User


class LabelPrintError(ValueError):
    pass


def mark_serial_labels_printed_once(db: Session, user: User, serial_ids: list[int]) -> list[Serial]:
    ids = list(dict.fromkeys(serial_ids))
    if not ids:
        raise LabelPrintError("No labels selected")

    serials = db.scalars(select(Serial).where(Serial.id.in_(ids))).all()
    if len(serials) != len(ids):
        raise LabelPrintError("Some labels were not found")

    already_printed = [serial.serial_number for serial in serials if serial.label_printed_at]
    if already_printed:
        joined = ", ".join(sorted(already_printed)[:5])
        suffix = "..." if len(already_printed) > 5 else ""
        raise LabelPrintError(f"Print option already used for {joined}{suffix}")

    printed_at = datetime.now(timezone.utc)
    for serial in serials:
        serial.label_printed_at = printed_at
        serial.label_printed_by_id = user.id
    db.commit()
    return serials
