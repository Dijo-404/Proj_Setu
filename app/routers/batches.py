from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_permission
from app.database import get_db
from app.models import AuditFinding, Batch, BatchItem, BatchStatus, BatchType, Product, Serial, SyncAttempt
from app.services.audit import reconcile_audit_batch, summarize_audit_findings
from app.services.exports import audit_report_pdf
from app.services.expiry import add_fefo_serials_to_batch
from app.services.inventory import (
    InventoryError,
    add_serial_to_batch,
    apply_batch_statuses,
    create_batch,
    remove_batch_item,
    update_batch_item_rate,
    update_product_rate_in_batch,
)
from app.services.access_control import role_has_access
from app.services.settings import get_all_settings
from app.services.tally import TallySyncError, build_voucher_xml, sync_batch
from app.services.voucher import calculate_voucher_summary, validate_priced_batch
from app.templates import templates

router = APIRouter(prefix="/batches")


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def action_key_for_batch(batch_type: BatchType) -> str:
    return {
        BatchType.PURCHASE: "batch_purchase",
        BatchType.RECEIVE: "batch_purchase",
        BatchType.SALE: "batch_sale",
        BatchType.AUDIT: "batch_audit",
        BatchType.SALES_RETURN: "batch_sales_return",
        BatchType.PURCHASE_RETURN: "batch_purchase_return",
        BatchType.ISSUE: "batch_issue",
        BatchType.QR_ASSIGNMENT: "barcode_assignment",
    }[batch_type]


def data_key_for_batch(batch_type: BatchType) -> str:
    return {
        BatchType.PURCHASE: "purchase_data",
        BatchType.RECEIVE: "purchase_data",
        BatchType.SALE: "sales_data",
        BatchType.AUDIT: "audit_data",
        BatchType.SALES_RETURN: "sales_data",
        BatchType.PURCHASE_RETURN: "purchase_data",
        BatchType.ISSUE: "issue_data",
        BatchType.QR_ASSIGNMENT: "barcode_assignment",
    }[batch_type]


def can_use_manual_scan(db: Session, user) -> bool:
    return role_has_access(db, user.role, "manual_serial_entry", {"edit", "yes"})


def scan_source_allowed(db: Session, user, scan_source: str) -> bool:
    return can_use_manual_scan(db, user) or scan_source == "camera"


def parse_batch_type(value: str) -> BatchType:
    try:
        return BatchType(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid batch type") from exc


@router.get("")
def batches(request: Request, db: Session = Depends(get_db)):
    user = require_permission(request, db, "batch_list")
    rows = db.scalars(select(Batch).order_by(desc(Batch.created_at)).limit(80)).all()
    return templates.TemplateResponse(request, "batches.html", {"request": request, "user": user, "batches": rows})


@router.get("/new")
def new_batch(request: Request, batch_type: str = BatchType.PURCHASE.value, db: Session = Depends(get_db)):
    parsed = parse_batch_type(batch_type)
    user = require_permission(request, db, action_key_for_batch(parsed))
    return templates.TemplateResponse(
        request,
        "batch_new.html",
        {"request": request, "user": user, "batch_type": parsed, "error": None},
    )


@router.post("")
def create_batch_route(
    request: Request,
    batch_type: str = Form(...),
    party_name: str = Form(""),
    reason_code: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    parsed = parse_batch_type(batch_type)
    user = require_permission(request, db, action_key_for_batch(parsed))
    batch = create_batch(db, user, parsed, party_name, notes, reason_code)
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.get("/{batch_id}")
def batch_detail(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(
            selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product),
            selectinload(Batch.sync_attempts),
            selectinload(Batch.audit_findings).selectinload(AuditFinding.serial),
        )
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    if batch.batch_type == BatchType.QR_ASSIGNMENT.value:
        return RedirectResponse(f"/barcode-assignment/{batch.id}", status_code=303)
    user = require_permission(request, db, data_key_for_batch(BatchType(batch.batch_type)))
    return templates.TemplateResponse(
        request,
        "batch_detail.html",
        {
            "request": request,
            "user": user,
            "batch": batch,
            "products": db.scalars(select(Product).where(Product.active == True).order_by(Product.product_code)).all(),
            "summary": calculate_voucher_summary(batch),
            "audit_summary": summarize_audit_findings(batch),
            "can_manual_scan": can_use_manual_scan(db, user),
            "error": None,
        },
    )


@router.post("/{batch_id}/scan")
def scan_into_batch(
    request: Request,
    batch_id: int,
    serial_number: str = Form(...),
    scan_source: str = Form("manual"),
    db: Session = Depends(get_db),
):
    batch = db.get(Batch, batch_id)
    if not batch:
        return JSONResponse({"ok": False, "error": "Batch not found"}, status_code=404)
    user = require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    if not scan_source_allowed(db, user, scan_source):
        return JSONResponse({"ok": False, "error": "Use camera scan to add serials"}, status_code=403)
    try:
        item = add_serial_to_batch(db, batch, user, serial_number)
    except InventoryError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "ok": True,
            "serial": item.serial.serial_number,
            "product": item.serial.product.product_name,
            "status": item.serial.status,
        }
    )


@router.post("/{batch_id}/fefo")
def fefo_pick_into_batch(
    request: Request,
    batch_id: int,
    product_id: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_db),
):
    batch = db.get(Batch, batch_id)
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    user = require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    require_permission(request, db, "fefo_pick", {"edit", "yes"})
    try:
        add_fefo_serials_to_batch(db, batch, user, product_id, quantity)
    except InventoryError as exc:
        batch = db.scalar(
            select(Batch)
            .where(Batch.id == batch_id)
            .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
        ) or batch
        return templates.TemplateResponse(
            request,
            "batch_detail.html",
            {
                "request": request,
                "user": user,
                "batch": batch,
                "products": db.scalars(select(Product).where(Product.active == True).order_by(Product.product_code)).all(),
                "summary": calculate_voucher_summary(batch),
                "audit_summary": summarize_audit_findings(batch),
                "can_manual_scan": can_use_manual_scan(db, user),
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/items/{item_id}/delete")
def delete_batch_item(request: Request, batch_id: int, item_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    try:
        remove_batch_item(db, batch, item_id)
    except InventoryError:
        pass
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/items/{item_id}/rate")
def update_item_rate(
    request: Request,
    batch_id: int,
    item_id: int,
    rate: float = Form(...),
    db: Session = Depends(get_db),
):
    batch = db.get(Batch, batch_id)
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    try:
        update_batch_item_rate(db, batch, item_id, rate)
    except InventoryError as exc:
        if wants_json(request):
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    if wants_json(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/products/{product_id}/rate")
def update_product_rate(
    request: Request,
    batch_id: int,
    product_id: int,
    rate: float = Form(...),
    db: Session = Depends(get_db),
):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    try:
        update_product_rate_in_batch(db, batch, product_id, rate)
    except InventoryError as exc:
        if wants_json(request):
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    if wants_json(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/submit")
def submit_batch(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    user = require_permission(request, db, action_key_for_batch(BatchType(batch.batch_type)))
    if batch.status != BatchStatus.DRAFT.value:
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    try:
        validate_priced_batch(batch)
        apply_batch_statuses(db, batch, user)
        if batch.batch_type == BatchType.AUDIT.value:
            reconcile_audit_batch(db, batch)
    except (InventoryError, ValueError) as exc:
        return templates.TemplateResponse(
            request,
            "batch_detail.html",
            {
                "request": request,
                "user": user,
                "batch": batch,
                "products": db.scalars(select(Product).where(Product.active == True).order_by(Product.product_code)).all(),
                "summary": calculate_voucher_summary(batch),
                "audit_summary": summarize_audit_findings(batch),
                "can_manual_scan": can_use_manual_scan(db, user),
                "error": str(exc),
            },
            status_code=400,
        )
    db.commit()
    sync_batch(db, batch)
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.post("/{batch_id}/retry")
def retry_batch(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, "tally_sync_retry", {"edit", "yes"})
    if batch.status in {BatchStatus.PENDING_SYNC.value, BatchStatus.FAILED.value, BatchStatus.SUBMITTED.value}:
        sync_batch(db, batch)
    return RedirectResponse(f"/batches/{batch.id}", status_code=303)


@router.get("/{batch_id}/audit.pdf")
def audit_pdf(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(selectinload(Batch.audit_findings), selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, data_key_for_batch(BatchType(batch.batch_type)))
    if batch.batch_type != BatchType.AUDIT.value:
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    return Response(
        audit_report_pdf(batch),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={batch.batch_number}-audit.pdf"},
    )


@router.get("/{batch_id}/tally.xml")
def tally_xml_preview(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(selectinload(Batch.items).selectinload(BatchItem.serial).selectinload(Serial.product))
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, "tally_xml", {"edit", "yes"})
    if batch.batch_type == BatchType.AUDIT.value:
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    if batch.batch_type not in {BatchType.PURCHASE.value, BatchType.RECEIVE.value, BatchType.SALE.value}:
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    try:
        xml = build_voucher_xml(batch, get_all_settings(db))
    except TallySyncError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(
        xml,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={batch.batch_number}-tally.xml"},
    )


@router.get("/{batch_id}/sync-attempts/{attempt_id}")
def sync_attempt_detail(request: Request, batch_id: int, attempt_id: int, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    attempt = db.get(SyncAttempt, attempt_id)
    if not batch or not attempt or attempt.batch_id != batch.id:
        return RedirectResponse("/batches", status_code=303)
    user = require_permission(request, db, "tally_attempts")
    return templates.TemplateResponse(
        request,
        "sync_attempt_detail.html",
        {"request": request, "user": user, "batch": batch, "attempt": attempt},
    )
