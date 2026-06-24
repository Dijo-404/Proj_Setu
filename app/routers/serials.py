from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_user
from app.database import get_db
from app.models import InventoryTransaction, Product, ScanLog, Serial
from app.services.exports import barcode_labels_pdf, barcode_png, serials_xlsx
from app.templates import templates

router = APIRouter(prefix="/serials")


@router.get("")
def serials(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    user = require_user(request, db)
    query = select(Serial).join(Product).order_by(Serial.created_at.desc()).limit(250)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Serial.serial_number.ilike(like), Product.product_code.ilike(like), Product.product_name.ilike(like)))
    if status:
        query = query.where(Serial.status == status)
    rows = db.scalars(query).all()
    return templates.TemplateResponse(
        request,
        "serials.html",
        {"request": request, "user": user, "serials": rows, "q": q, "status": status},
    )


@router.get("/{serial_id}/barcode.png")
def serial_barcode(serial_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    serial = db.get(Serial, serial_id)
    if not serial:
        raise HTTPException(status_code=404)
    return Response(barcode_png(serial.serial_number), media_type="image/png")


@router.get("/labels")
def labels(request: Request, ids: str = "", db: Session = Depends(get_db)):
    user = require_user(request, db)
    parsed = [int(value) for value in ids.split(",") if value.strip().isdigit()]
    rows = db.scalars(
        select(Serial).where(Serial.id.in_(parsed)).order_by(Serial.serial_number).options(selectinload(Serial.product))
    ).all() if parsed else []
    return templates.TemplateResponse(request, "labels.html", {"request": request, "user": user, "serials": rows})


@router.get("/labels.pdf")
def labels_pdf(request: Request, ids: str = "", db: Session = Depends(get_db)):
    require_user(request, db)
    parsed = [int(value) for value in ids.split(",") if value.strip().isdigit()]
    rows = db.scalars(
        select(Serial).where(Serial.id.in_(parsed)).order_by(Serial.serial_number).options(selectinload(Serial.product))
    ).all() if parsed else []
    return Response(
        barcode_labels_pdf(rows),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=setu-barcode-labels.pdf"},
    )


@router.get("/labels.xlsx")
def labels_xlsx(request: Request, ids: str = "", db: Session = Depends(get_db)):
    require_user(request, db)
    parsed = [int(value) for value in ids.split(",") if value.strip().isdigit()]
    rows = db.scalars(
        select(Serial).where(Serial.id.in_(parsed)).order_by(Serial.serial_number).options(selectinload(Serial.product))
    ).all() if parsed else []
    return Response(
        serials_xlsx(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-barcodes.xlsx"},
    )


@router.get("/{serial_id}")
def serial_detail(serial_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    serial = db.scalar(select(Serial).where(Serial.id == serial_id).options(selectinload(Serial.product)))
    if not serial:
        raise HTTPException(status_code=404)
    transactions = db.scalars(
        select(InventoryTransaction)
        .where(InventoryTransaction.serial_id == serial.id)
        .order_by(InventoryTransaction.created_at)
        .options(
            selectinload(InventoryTransaction.user),
            selectinload(InventoryTransaction.batch),
            selectinload(InventoryTransaction.product),
        )
    ).all()
    logs = db.scalars(
        select(ScanLog)
        .where(ScanLog.serial_id == serial.id)
        .order_by(desc(ScanLog.created_at))
        .limit(80)
        .options(selectinload(ScanLog.user), selectinload(ScanLog.batch))
    ).all()
    replacement = db.get(Serial, serial.replaced_by_id) if serial.replaced_by_id else None
    return templates.TemplateResponse(
        request,
        "serial_detail.html",
        {
            "request": request,
            "user": user,
            "serial": serial,
            "transactions": transactions,
            "logs": logs,
            "replacement": replacement,
        },
    )
