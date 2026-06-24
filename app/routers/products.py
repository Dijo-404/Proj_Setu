from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import ADMIN_ROLES, require_user
from app.database import get_db
from app.models import Product, SerialStatus
from app.services.assignment import AssignmentLine, assign_barcodes_to_existing_stock
from app.services.inventory import InventoryError
from app.templates import templates

router = APIRouter(prefix="/products")


@router.get("")
def products(request: Request, q: str = "", error: str = "", db: Session = Depends(get_db)):
    user = require_user(request, db)
    error_message = {"serial_generation_failed": "Barcode generation failed"}.get(error, error)
    query = select(Product).order_by(Product.product_code)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Product.product_code.ilike(like), Product.product_name.ilike(like)))
    rows = db.scalars(query).all()
    return templates.TemplateResponse(
        request,
        "products.html",
        {"request": request, "user": user, "products": rows, "q": q, "error": error_message or None},
    )


@router.post("")
def create_product(
    request: Request,
    product_code: str = Form(...),
    product_name: str = Form(...),
    category: str = Form(""),
    hsn: str = Form(...),
    gst_rate: float = Form(...),
    unit: str = Form("Pcs"),
    default_rate: float = Form(0),
    tally_stock_item_name: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db, ADMIN_ROLES)
    product = Product(
        product_code=product_code.strip().upper(),
        product_name=product_name.strip(),
        category=category.strip() or None,
        hsn=hsn.strip(),
        gst_rate=gst_rate,
        unit=unit.strip() or "Pcs",
        default_rate=default_rate,
        tally_stock_item_name=tally_stock_item_name.strip() or product_name.strip(),
    )
    db.add(product)
    try:
        db.commit()
    except Exception:
        db.rollback()
        rows = db.scalars(select(Product).order_by(Product.product_code)).all()
        return templates.TemplateResponse(
            request,
            "products.html",
            {"request": request, "user": user, "products": rows, "q": "", "error": "Product code already exists"},
            status_code=400,
        )
    return RedirectResponse("/products", status_code=303)


@router.post("/{product_id}/generate")
def generate_product_serials(
    request: Request,
    product_id: int,
    quantity: int = Form(...),
    prefix: str = Form(""),
    initial_status: str = Form(SerialStatus.GENERATED.value),
    db: Session = Depends(get_db),
):
    user = require_user(request, db, ADMIN_ROLES)
    product = db.get(Product, product_id)
    if not product:
        return RedirectResponse("/products", status_code=303)
    try:
        parsed_status = SerialStatus(initial_status)
        batch = assign_barcodes_to_existing_stock(
            db,
            user,
            [AssignmentLine(product=product, quantity=quantity, prefix=prefix or None)],
            source="MANUAL" if parsed_status == SerialStatus.IN_STOCK else "GENERATED",
            initial_status=parsed_status,
        )
    except (InventoryError, ValueError):
        return RedirectResponse(f"/products?error=serial_generation_failed", status_code=303)
    return RedirectResponse(f"/barcode-assignment/{batch.id}", status_code=303)
