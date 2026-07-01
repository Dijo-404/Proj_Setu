from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_permission
from app.database import get_db
from app.models import (
    AuditFinding,
    Batch,
    BatchItem,
    BatchStatus,
    BatchType,
    GstRegistrationType,
    GstTreatment,
    Product,
    Serial,
    SyncAttempt,
)
from app.services.audit import reconcile_audit_batch, summarize_audit_findings
from app.services.exports import audit_report_pdf
from app.services.expiry import add_fefo_serials_to_batch
from app.services.inventory import (
    DEFAULT_UNREGISTERED_SALE_STATE,
    InventoryError,
    add_serial_to_batch,
    apply_batch_statuses,
    create_batch,
    gst_registration_requires_gstin,
    normalize_gst_registration_type,
    normalize_gstin,
    remove_batch_item,
    update_batch_item_rate,
    update_product_rate_in_batch,
)
from app.services.preinvoice import sale_preinvoice_pdf
from app.services.access_control import role_has_access
from app.services.settings import get_all_settings
from app.services.relocation import find_location_by_code
from app.services.shelf_verification import (
    ShelfVerificationError,
    ensure_product_scan_allowed,
    shelf_verification_state,
    verify_pending_items_on_shelf,
)
from app.services.tally import TALLY_XML_SUPPORTED_BATCH_TYPES, TallySyncError, build_voucher_xml, sync_batch
from app.services.voucher import calculate_voucher_summary, validate_priced_batch
from app.templates import templates

router = APIRouter(prefix="/batches")


INDIAN_STATE_OPTIONS = (
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
)
GST_TREATMENT_OPTIONS = (
    (GstTreatment.INTRA_STATE.value, "CGST + SGST"),
    (GstTreatment.INTER_STATE.value, "IGST"),
)
GST_REGISTRATION_OPTIONS = tuple(
    (
        registration_type.value,
        "Registered" if registration_type == GstRegistrationType.REGULAR else registration_type.value,
    )
    for registration_type in GstRegistrationType
)

BATCH_LIST_SCOPES = {
    "all": {
        "title": "Batches",
        "eyebrow": "Transactions",
        "permission": "batch_list",
        "types": None,
        "empty_message": "No batches yet",
    },
    "purchase": {
        "title": "Purchase batches",
        "eyebrow": "Incoming stock",
        "permission": "purchase_data",
        "types": (BatchType.PURCHASE.value, BatchType.RECEIVE.value),
        "empty_message": "No purchase batches yet",
    },
    "sales": {
        "title": "Sales batches",
        "eyebrow": "Outgoing stock",
        "permission": "sales_data",
        "types": (BatchType.SALE.value,),
        "empty_message": "No sales batches yet",
    },
}


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


def batch_permission_context(db: Session, user, batch: Batch) -> dict[str, bool]:
    action_key = action_key_for_batch(BatchType(batch.batch_type))
    can_edit = role_has_access(db, user.role, action_key)
    return {
        "can_edit_batch": can_edit,
        "can_fefo": can_edit and role_has_access(db, user.role, "fefo_pick", {"edit", "yes"}),
        "can_tally_xml": role_has_access(db, user.role, "tally_xml", {"edit", "yes"}),
        "can_retry_sync": role_has_access(db, user.role, "tally_sync_retry", {"edit", "yes"}),
        "can_view_attempts": role_has_access(db, user.role, "tally_attempts"),
        "can_view_batch_list": role_has_access(db, user.role, "batch_list"),
    }


def parse_batch_type(value: str) -> BatchType:
    try:
        return BatchType(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid batch type") from exc


def batch_form_context(
    request: Request,
    user,
    batch_type: BatchType,
    *,
    party_name: str = "",
    party_state: str = "",
    party_gst_registration_type: str | None = None,
    party_gst_name: str = "",
    party_gstin: str = "",
    gst_treatment: str | None = None,
    gst_cgst_rate: str = "",
    gst_sgst_rate: str = "",
    gst_igst_rate: str = "",
    notes: str = "",
    error: str | None = None,
) -> dict[str, object]:
    selected_registration = party_gst_registration_type or GstRegistrationType.UNREGISTERED_CONSUMER.value
    selected_state = party_state
    if batch_type == BatchType.SALE and not selected_state and selected_registration == GstRegistrationType.UNREGISTERED_CONSUMER.value:
        selected_state = DEFAULT_UNREGISTERED_SALE_STATE
    return {
        "request": request,
        "user": user,
        "batch_type": batch_type,
        "party_name": party_name,
        "party_state": selected_state,
        "party_gst_registration_type": (
            selected_registration
        ),
        "party_gst_name": party_gst_name,
        "party_gstin": party_gstin,
        "gst_registration_options": GST_REGISTRATION_OPTIONS,
        "gst_treatment": gst_treatment or GstTreatment.INTRA_STATE.value,
        "gst_cgst_rate": gst_cgst_rate,
        "gst_sgst_rate": gst_sgst_rate,
        "gst_igst_rate": gst_igst_rate,
        "gst_treatment_options": GST_TREATMENT_OPTIONS,
        "state_options": INDIAN_STATE_OPTIONS,
        "notes": notes,
        "error": error,
    }


def parse_optional_gst_rate(value: str, label: str) -> float | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        rate = float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if rate < 0 or rate > 100:
        raise ValueError(f"{label} must be between 0 and 100%.")
    return rate


def batch_list_rows(db: Session, batch_types: tuple[str, ...] | None = None) -> list[Batch]:
    query = select(Batch).options(selectinload(Batch.items))
    if batch_types:
        query = query.where(Batch.batch_type.in_(batch_types))
    return db.scalars(query.order_by(desc(Batch.created_at)).limit(80)).all()


def batch_list_response(request: Request, db: Session, scope: str):
    config = BATCH_LIST_SCOPES[scope]
    user = require_permission(request, db, config["permission"])
    return templates.TemplateResponse(
        request,
        "batches.html",
        {
            "request": request,
            "user": user,
            "batches": batch_list_rows(db, config["types"]),
            "batch_scope": scope,
            "page_title": config["title"],
            "page_eyebrow": config["eyebrow"],
            "empty_message": config["empty_message"],
        },
    )


@router.get("")
def batches(request: Request, db: Session = Depends(get_db)):
    return batch_list_response(request, db, "all")


@router.get("/purchase")
def purchase_batches(request: Request, db: Session = Depends(get_db)):
    return batch_list_response(request, db, "purchase")


@router.get("/sales")
def sales_batches(request: Request, db: Session = Depends(get_db)):
    return batch_list_response(request, db, "sales")


@router.get("/new")
def new_batch(request: Request, batch_type: str = BatchType.PURCHASE.value, db: Session = Depends(get_db)):
    parsed = parse_batch_type(batch_type)
    user = require_permission(request, db, action_key_for_batch(parsed))
    return templates.TemplateResponse(
        request,
        "batch_new.html",
        batch_form_context(request, user, parsed),
    )


@router.post("")
def create_batch_route(
    request: Request,
    batch_type: str = Form(...),
    party_name: str = Form(""),
    party_state: str = Form(""),
    party_gst_registration_type: str = Form(""),
    party_gst_name: str = Form(""),
    party_gstin: str = Form(""),
    gst_cgst_rate: str = Form(""),
    gst_sgst_rate: str = Form(""),
    gst_igst_rate: str = Form(""),
    reason_code: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    parsed = parse_batch_type(batch_type)
    user = require_permission(request, db, action_key_for_batch(parsed))
    party_state = party_state.strip() if parsed == BatchType.SALE else ""
    selected_gst_registration_type = ""
    selected_gst_treatment = ""
    cgst_rate = sgst_rate = igst_rate = None
    if parsed == BatchType.SALE:
        try:
            selected_gst_registration_type = normalize_gst_registration_type(
                party_gst_registration_type,
                parsed,
            ) or ""
            if (
                selected_gst_registration_type == GstRegistrationType.UNREGISTERED_CONSUMER.value
                and not party_state
            ):
                party_state = DEFAULT_UNREGISTERED_SALE_STATE
            if gst_registration_requires_gstin(selected_gst_registration_type):
                normalize_gstin(party_gstin)
            cgst_rate = parse_optional_gst_rate(gst_cgst_rate, "CGST")
            sgst_rate = parse_optional_gst_rate(gst_sgst_rate, "SGST")
            igst_rate = parse_optional_gst_rate(gst_igst_rate, "IGST")
            if igst_rate is not None:
                if cgst_rate is not None or sgst_rate is not None:
                    raise ValueError("Enter either IGST, or CGST and SGST. Do not enter both.")
                cgst_rate = None
                sgst_rate = None
                selected_gst_treatment = GstTreatment.INTER_STATE.value
            else:
                if (cgst_rate is None) != (sgst_rate is None):
                    raise ValueError("Enter both CGST and SGST values, or leave both blank.")
                selected_gst_treatment = GstTreatment.INTRA_STATE.value
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "batch_new.html",
                batch_form_context(
                    request,
                    user,
                    parsed,
                    party_name=party_name,
                    party_state=party_state,
                    party_gst_registration_type=(
                        selected_gst_registration_type or party_gst_registration_type
                    ),
                    party_gst_name=party_gst_name,
                    party_gstin=party_gstin,
                    gst_treatment=selected_gst_treatment,
                    gst_cgst_rate=gst_cgst_rate,
                    gst_sgst_rate=gst_sgst_rate,
                    gst_igst_rate=gst_igst_rate,
                    notes=notes,
                    error=str(exc),
                ),
                status_code=400,
            )
    party_required = parsed in {
        BatchType.SALE,
        BatchType.SALES_RETURN,
        BatchType.PURCHASE,
        BatchType.RECEIVE,
        BatchType.PURCHASE_RETURN,
    }
    if party_required and not party_name.strip():
        party_label = "Customer" if parsed in {BatchType.SALE, BatchType.SALES_RETURN} else "Supplier"
        return templates.TemplateResponse(
            request,
            "batch_new.html",
            batch_form_context(
                request,
                user,
                parsed,
                party_name=party_name,
                party_state=party_state,
                party_gst_registration_type=(
                    selected_gst_registration_type or party_gst_registration_type
                ),
                party_gst_name=party_gst_name,
                party_gstin=party_gstin,
                gst_treatment=selected_gst_treatment,
                gst_cgst_rate=gst_cgst_rate,
                gst_sgst_rate=gst_sgst_rate,
                gst_igst_rate=gst_igst_rate,
                notes=notes,
                error=f"{party_label} is required.",
            ),
            status_code=400,
        )
    batch = create_batch(
        db,
        user,
        parsed,
        party_name,
        notes,
        reason_code,
        party_state=party_state if parsed == BatchType.SALE else None,
        party_gst_registration_type=(
            selected_gst_registration_type if parsed == BatchType.SALE else None
        ),
        party_gst_name=party_gst_name if parsed == BatchType.SALE else None,
        party_gstin=party_gstin if parsed == BatchType.SALE else None,
        gst_treatment=selected_gst_treatment if parsed == BatchType.SALE else None,
        gst_cgst_rate=cgst_rate,
        gst_sgst_rate=sgst_rate,
        gst_igst_rate=igst_rate,
    )
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
            "shelf_state": shelf_verification_state(batch),
            "can_manual_scan": can_use_manual_scan(db, user),
            **batch_permission_context(db, user, batch),
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
    location = find_location_by_code(db, serial_number)
    if location:
        try:
            verified_count = verify_pending_items_on_shelf(
                db,
                batch=batch,
                location=location,
                user=user,
            )
        except ShelfVerificationError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    **shelf_verification_state(batch),
                },
                status_code=400,
            )
        return JSONResponse(
            {
                "ok": True,
                "scan_type": "shelf",
                "location_code": location.code,
                "location": location.full_path,
                "verified_count": verified_count,
                **shelf_verification_state(batch),
            }
        )
    try:
        ensure_product_scan_allowed(batch)
        item = add_serial_to_batch(db, batch, user, serial_number)
    except (InventoryError, ShelfVerificationError) as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), **shelf_verification_state(batch)},
            status_code=400,
        )
    return JSONResponse(
        {
            "ok": True,
            "scan_type": "product",
            "serial": item.serial.serial_number,
            "product": item.serial.product.product_name,
            "status": item.serial.status,
            **shelf_verification_state(batch),
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
                "shelf_state": shelf_verification_state(batch),
                "can_manual_scan": can_use_manual_scan(db, user),
                **batch_permission_context(db, user, batch),
                "fefo_error": str(exc),
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
        db.rollback()
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
                "shelf_state": shelf_verification_state(batch),
                "can_manual_scan": can_use_manual_scan(db, user),
                **batch_permission_context(db, user, batch),
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


@router.get("/{batch_id}/preinvoice.pdf")
def sale_preinvoice(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id)
        .options(
            selectinload(Batch.items)
            .selectinload(BatchItem.serial)
            .selectinload(Serial.product)
        )
    )
    if not batch:
        return RedirectResponse("/batches", status_code=303)
    require_permission(request, db, "sales_data")
    if batch.batch_type != BatchType.SALE.value:
        return RedirectResponse(f"/batches/{batch.id}", status_code=303)
    if not batch.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one item before generating a pre-invoice.",
        )
    return Response(
        sale_preinvoice_pdf(batch, get_all_settings(db)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename={batch.batch_number}-preinvoice.pdf"
            )
        },
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
    if batch.batch_type not in TALLY_XML_SUPPORTED_BATCH_TYPES:
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
