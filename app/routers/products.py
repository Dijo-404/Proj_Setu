from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import require_permission, require_user
from app.database import get_db
from app.models import InventoryTransaction, Product, Role, Serial, SerialStatus, WarehouseLevel
from app.services.assignment import AssignmentLine, assign_barcodes_to_existing_stock
from app.services.expiry import parse_optional_date
from app.services.inventory import InventoryError
from app.templates import templates

router = APIRouter(prefix="/products")


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


@router.get("")
def products(request: Request, q: str = "", error: str = "", db: Session = Depends(get_db)):
    user = require_permission(request, db, "product_master")
    error_message = {
        "serial_generation_failed": "Barcode generation failed",
        "default_rate_invalid": "Default rate cannot be negative",
        "sales_discount_invalid": "Sales discount must be between 0 and 100%",
        "shelf_interval_invalid": "Shelf verification interval must be between 1 and 1000 scans",
        "product_delete_blocked": "Product has serials or transaction history and cannot be deleted",
    }.get(error, error)
    query = select(Product).order_by(Product.product_code)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Product.product_code.ilike(like), Product.product_name.ilike(like)))
    rows = db.scalars(query).all()
    return templates.TemplateResponse(
        request,
        "products.html",
        {
            "request": request,
            "user": user,
            "products": rows,
            "warehouse_levels": [level.value for level in WarehouseLevel],
            "q": q,
            "error": error_message or None,
        },
    )


@router.post("")
def create_product(
    request: Request,
    product_code: str = Form(...),
    product_name: str = Form(...),
    category: str = Form(""),
    brand: str = Form(""),
    hsn: str = Form(...),
    gst_rate: float = Form(...),
    unit: str = Form("Pcs"),
    default_rate: float = Form(0),
    sales_discount_rate: float = Form(0),
    shelf_verification_interval: int = Form(1),
    tally_stock_item_name: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "product_create")
    if sales_discount_rate < 0 or sales_discount_rate > 100:
        rows = db.scalars(select(Product).order_by(Product.product_code)).all()
        return templates.TemplateResponse(
            request,
            "products.html",
            {
                "request": request,
                "user": user,
                "products": rows,
                "warehouse_levels": [level.value for level in WarehouseLevel],
                "q": "",
                "error": "Sales discount must be between 0 and 100%",
            },
            status_code=400,
        )
    if shelf_verification_interval < 1 or shelf_verification_interval > 1000:
        rows = db.scalars(select(Product).order_by(Product.product_code)).all()
        return templates.TemplateResponse(
            request,
            "products.html",
            {
                "request": request,
                "user": user,
                "products": rows,
                "warehouse_levels": [level.value for level in WarehouseLevel],
                "q": "",
                "error": "Shelf verification interval must be between 1 and 1000 scans",
            },
            status_code=400,
        )
    product = Product(
        product_code=product_code.strip().upper(),
        product_name=product_name.strip(),
        category=category.strip() or None,
        brand=brand.strip() or None,
        hsn=hsn.strip(),
        gst_rate=gst_rate,
        unit=unit.strip() or "Pcs",
        default_rate=default_rate,
        sales_discount_rate=sales_discount_rate,
        shelf_verification_interval=shelf_verification_interval,
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
            {
                "request": request,
                "user": user,
                "products": rows,
                "warehouse_levels": [level.value for level in WarehouseLevel],
                "q": "",
                "error": "Product code already exists",
            },
            status_code=400,
        )
    return RedirectResponse("/products", status_code=303)


@router.api_route("/{product_id}/name", methods=["GET", "POST"])
def product_name_legacy_redirect(request: Request, product_id: int, db: Session = Depends(get_db)):
    require_permission(request, db, "product_master")
    return RedirectResponse("/products", status_code=303)


@router.post("/{product_id}/delete")
def delete_product(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
):
    require_user(request, db, {Role.SUPER_ADMIN})
    product = db.get(Product, product_id)
    if not product:
        return RedirectResponse("/products", status_code=303)

    serial_count = db.scalar(select(func.count(Serial.id)).where(Serial.product_id == product.id)) or 0
    transaction_count = db.scalar(select(func.count(InventoryTransaction.id)).where(InventoryTransaction.product_id == product.id)) or 0
    if serial_count or transaction_count:
        return RedirectResponse("/products?error=product_delete_blocked", status_code=303)

    db.delete(product)
    db.commit()
    return RedirectResponse("/products", status_code=303)


@router.post("/{product_id}/pricing")
def update_product_pricing(
    request: Request,
    product_id: int,
    default_rate: float = Form(0),
    sales_discount_rate: float = Form(0),
    shelf_verification_interval: int | None = Form(None),
    category: str | None = Form(None),
    brand: str | None = Form(None),
    db: Session = Depends(get_db),
):
    require_permission(request, db, "product_create")
    product = db.get(Product, product_id)
    if not product:
        if wants_json(request):
            return JSONResponse({"ok": False, "error": "Product not found"}, status_code=404)
        return RedirectResponse("/products", status_code=303)
    if default_rate < 0:
        if wants_json(request):
            return JSONResponse({"ok": False, "error": "Default rate cannot be negative"}, status_code=400)
        return RedirectResponse("/products?error=default_rate_invalid", status_code=303)
    if sales_discount_rate < 0 or sales_discount_rate > 100:
        if wants_json(request):
            return JSONResponse({"ok": False, "error": "Sales discount must be between 0 and 100%"}, status_code=400)
        return RedirectResponse("/products?error=sales_discount_invalid", status_code=303)
    if shelf_verification_interval is not None and (
        shelf_verification_interval < 1 or shelf_verification_interval > 1000
    ):
        if wants_json(request):
            return JSONResponse(
                {"ok": False, "error": "Shelf verification interval must be between 1 and 1000 scans"},
                status_code=400,
            )
        return RedirectResponse("/products?error=shelf_interval_invalid", status_code=303)
    product.default_rate = default_rate
    product.sales_discount_rate = sales_discount_rate
    if shelf_verification_interval is not None:
        product.shelf_verification_interval = shelf_verification_interval
    elif not product.shelf_verification_interval or product.shelf_verification_interval < 1:
        product.shelf_verification_interval = 1
    if category is not None:
        product.category = category.strip() or None
    if brand is not None:
        product.brand = brand.strip() or None
    db.commit()
    db.refresh(product)
    if wants_json(request):
        return JSONResponse(
            {
                "ok": True,
                "product": {
                    "id": product.id,
                    "category": product.category or "",
                    "brand": product.brand or "",
                    "default_rate": float(product.default_rate or 0),
                    "sales_discount_rate": float(product.sales_discount_rate or 0),
                    "shelf_verification_interval": int(product.shelf_verification_interval),
                },
            }
        )
    return RedirectResponse("/products", status_code=303)


@router.post("/{product_id}/generate")
def generate_product_serials(
    request: Request,
    product_id: int,
    quantity: int = Form(...),
    prefix: str = Form(""),
    initial_status: str = Form(SerialStatus.GENERATED.value),
    product_batch_number: str = Form(""),
    mfg_date: str = Form(""),
    expiry_date: str = Form(""),
    warehouse: str = Form(""),
    warehouse_level: str = Form(WarehouseLevel.COMPANY_WAREHOUSE.value),
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "product_create")
    product = db.get(Product, product_id)
    if not product:
        return RedirectResponse("/products", status_code=303)
    try:
        parsed_status = SerialStatus(initial_status)
        parsed_mfg_date = parse_optional_date(mfg_date)
        parsed_expiry_date = parse_optional_date(expiry_date)
        if parsed_mfg_date and parsed_expiry_date and parsed_expiry_date <= parsed_mfg_date:
            raise InventoryError("Expiry date must be after mfg date")
        batch = assign_barcodes_to_existing_stock(
            db,
            user,
            [
                AssignmentLine(
                    product=product,
                    quantity=quantity,
                    prefix=prefix or None,
                    product_batch_number=product_batch_number.strip() or None,
                    mfg_date=parsed_mfg_date,
                    expiry_date=parsed_expiry_date,
                    warehouse=warehouse.strip() or None,
                    warehouse_level=warehouse_level,
                )
            ],
            source="MANUAL" if parsed_status == SerialStatus.IN_STOCK else "GENERATED",
            initial_status=parsed_status,
        )
    except (InventoryError, ValueError):
        return RedirectResponse(f"/products?error=serial_generation_failed", status_code=303)
    return RedirectResponse(f"/barcode-assignment/{batch.id}", status_code=303)
