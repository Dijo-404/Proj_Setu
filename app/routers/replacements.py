from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.models import ScanLog
from app.services.inventory import InventoryError
from app.services.replacement import replace_qr_serial
from app.templates import templates

router = APIRouter(prefix="/qr-replacement")


@router.get("")
def replacement_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db, ADMIN_ROLES)
    logs = db.scalars(
        select(ScanLog).where(ScanLog.action == "QR_REPLACEMENT").order_by(desc(ScanLog.created_at)).limit(40)
    ).all()
    return templates.TemplateResponse(
        request,
        "qr_replacement.html",
        {"request": request, "user": user, "logs": logs, "error": None, "replacement": None},
    )


@router.post("")
def replace_qr(
    request: Request,
    old_serial_number: str = Form(...),
    new_serial_number: str = Form(""),
    reason: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db, ADMIN_ROLES)
    logs = db.scalars(
        select(ScanLog).where(ScanLog.action == "QR_REPLACEMENT").order_by(desc(ScanLog.created_at)).limit(40)
    ).all()
    try:
        replacement = replace_qr_serial(db, user, old_serial_number, new_serial_number or None, reason)
    except InventoryError as exc:
        return templates.TemplateResponse(
            request,
            "qr_replacement.html",
            {"request": request, "user": user, "logs": logs, "error": str(exc), "replacement": None},
            status_code=400,
        )
    logs = db.scalars(
        select(ScanLog).where(ScanLog.action == "QR_REPLACEMENT").order_by(desc(ScanLog.created_at)).limit(40)
    ).all()
    return templates.TemplateResponse(
        request,
        "qr_replacement.html",
        {"request": request, "user": user, "logs": logs, "error": None, "replacement": replacement},
    )
