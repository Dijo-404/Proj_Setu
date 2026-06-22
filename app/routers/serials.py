from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_user
from app.database import get_db
from app.models import Product, Serial
from app.services.exports import qr_labels_pdf
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


@router.get("/{serial_id}/qr.png")
def serial_qr(serial_id: int, db: Session = Depends(get_db)):
    serial = db.get(Serial, serial_id)
    if not serial:
        raise HTTPException(status_code=404)
    try:
        import qrcode
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="qrcode package is not installed") from exc
    image = qrcode.make(serial.serial_number)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png")


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
        qr_labels_pdf(rows),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=setu-qr-labels.pdf"},
    )
