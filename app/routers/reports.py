from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_permission
from app.database import get_db
from app.models import AuditFinding, Batch, InventoryTransaction, Product, Role, ScanLog, Serial, TransactionType, has_any_role, has_role
from app.services.audit import current_missing_stock_findings_query, refresh_expired_audit_assignments
from app.services.charts import bar_chart, donut_chart
from app.services.director_reports import director_audit_batch_report, director_audit_reconciliation_report, director_report
from app.services.expiry import expiry_summary
from app.services.exports import audit_reconciliation_xlsx, missing_stock_xlsx, scans_xlsx, transactions_xlsx
from app.services.losses import loss_summary
from app.services.log_fields import barcode_sold_by, invoice_created_by, product_audited_by
from app.templates import templates

router = APIRouter(prefix="/reports")
MISSING_STOCK_ACTION = "MISSING"


def parse_filter_date(value: str, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} date",
        ) from exc


def parse_period_datetime(value: str, field_name: str, *, end: bool = False) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} date/time",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    if end and len(raw) == 10:
        parsed = parsed + timedelta(days=1)
    return parsed


def export_url(path: str, params: dict[str, str]) -> str:
    filtered = {key: value for key, value in params.items() if value}
    return f"{path}?{urlencode(filtered)}" if filtered else path


def scan_query(action: str = "", start: str = "", end: str = ""):
    conditions = []
    if action:
        conditions.append(ScanLog.action == action)
    start_dt = parse_filter_date(start, "start")
    if start_dt:
        conditions.append(ScanLog.created_at >= start_dt)
    end_dt = parse_filter_date(end, "end")
    if end_dt:
        end_dt = end_dt + timedelta(days=1)
        conditions.append(ScanLog.created_at < end_dt)
    query = (
        select(ScanLog)
        .order_by(desc(ScanLog.created_at))
        .limit(500)
        .options(
            selectinload(ScanLog.user),
            selectinload(ScanLog.batch),
        )
    )
    if conditions:
        query = query.where(and_(*conditions))
    return query


def transaction_query(action: str = "", q: str = "", start: str = "", end: str = ""):
    conditions = []
    if action:
        conditions.append(InventoryTransaction.transaction_type == action)
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                InventoryTransaction.serial_number.ilike(like),
                InventoryTransaction.tally_reference.ilike(like),
                InventoryTransaction.reference_number.ilike(like),
                Product.product_code.ilike(like),
                Product.product_name.ilike(like),
            )
        )
    start_dt = parse_filter_date(start, "start")
    if start_dt:
        conditions.append(InventoryTransaction.created_at >= start_dt)
    end_dt = parse_filter_date(end, "end")
    if end_dt:
        end_dt = end_dt + timedelta(days=1)
        conditions.append(InventoryTransaction.created_at < end_dt)
    query = (
        select(InventoryTransaction)
        .outerjoin(Product, InventoryTransaction.product_id == Product.id)
        .order_by(desc(InventoryTransaction.created_at))
        .limit(500)
        .options(
            selectinload(InventoryTransaction.user),
            selectinload(InventoryTransaction.serial),
            selectinload(InventoryTransaction.product),
            selectinload(InventoryTransaction.batch).selectinload(Batch.user),
        )
    )
    if conditions:
        query = query.where(and_(*conditions))
    return query


def missing_stock_query(q: str = "", start: str = "", end: str = ""):
    conditions = []
    if q:
        like = f"%{q.strip()}%"
        conditions.append(
            or_(
                AuditFinding.serial_number.ilike(like),
                AuditFinding.product_code.ilike(like),
                AuditFinding.product_name.ilike(like),
                Batch.batch_number.ilike(like),
            )
        )
    start_dt = parse_filter_date(start, "start")
    if start_dt:
        conditions.append(AuditFinding.created_at >= start_dt)
    end_dt = parse_filter_date(end, "end")
    if end_dt:
        conditions.append(AuditFinding.created_at < end_dt + timedelta(days=1))
    query = current_missing_stock_findings_query().join(Batch, AuditFinding.batch_id == Batch.id)
    if conditions:
        query = query.where(and_(*conditions))
    return query.limit(500).options(
        selectinload(AuditFinding.batch).selectinload(Batch.user),
        selectinload(AuditFinding.serial).selectinload(Serial.location),
    )


@router.get("")
def reports(
    request: Request,
    action: str = "",
    q: str = "",
    start: str = "",
    end: str = "",
    audit_start: str = "",
    audit_end: str = "",
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "reports_data")
    refresh_expired_audit_assignments(db)
    if has_role(user.role, Role.DIRECTORS) and not has_any_role(user.role, {Role.ADMIN, Role.SUPER_ADMIN}):
        audit_start_dt = parse_period_datetime(audit_start, "audit start")
        audit_end_dt = parse_period_datetime(audit_end, "audit end", end=True)
        return templates.TemplateResponse(
            request,
            "director_reports.html",
            {
                "request": request,
                "user": user,
                "report": director_report(db, audit_start_dt, audit_end_dt),
                "audit_start": audit_start,
                "audit_end": audit_end,
                "audit_reconciliation_export_url": export_url(
                    "/reports/audit-reconciliation.xlsx",
                    {"start": audit_start, "end": audit_end},
                ),
            },
        )

    start_dt = parse_filter_date(start, "start")
    end_dt = parse_filter_date(end, "end")
    if end_dt:
        end_dt = end_dt + timedelta(days=1)
    missing_stock_selected = action == MISSING_STOCK_ACTION
    scans = [] if missing_stock_selected else db.scalars(scan_query(action, start, end)).all()
    transactions = [] if missing_stock_selected else db.scalars(transaction_query(action, q, start, end)).all()
    missing_stock = (
        db.scalars(missing_stock_query(q, start, end)).all()
        if not action or missing_stock_selected
        else []
    )
    transaction_counts = Counter(txn.transaction_type for txn in transactions)
    if missing_stock:
        transaction_counts[MISSING_STOCK_ACTION] = len(missing_stock)
    scan_status_counts = Counter(scan.status for scan in scans)
    pending = db.scalars(
        select(Batch)
        .where(Batch.status.in_(["PENDING_SYNC", "FAILED"]))
        .order_by(desc(Batch.created_at))
        .limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "request": request,
            "user": user,
            "scans": scans,
            "transactions": transactions,
            "missing_stock": missing_stock,
            "pending": pending,
            "transaction_chart": bar_chart(transaction_counts.items()),
            "scan_status_chart": donut_chart(scan_status_counts.items()),
            "expiry": expiry_summary(db),
            "losses": (
                loss_summary(db, action=action, q=q, start=start_dt, end=end_dt)
                if has_any_role(user.role, {Role.ADMIN, Role.SUPER_ADMIN})
                else None
            ),
            "action": action,
            "q": q,
            "start": start,
            "end": end,
            "transaction_types": [item.value for item in TransactionType] + [MISSING_STOCK_ACTION],
            "invoice_created_by": invoice_created_by,
            "barcode_sold_by": barcode_sold_by,
            "product_audited_by": product_audited_by,
            "audit_reconciliation_export_url": export_url(
                "/reports/audit-reconciliation.xlsx",
                {"start": start, "end": end},
            ),
        },
    )


@router.get("/missing-stock")
def missing_stock_report(
    request: Request,
    q: str = "",
    start: str = "",
    end: str = "",
    db: Session = Depends(get_db),
):
    user = require_permission(request, db, "reports_data")
    refresh_expired_audit_assignments(db)
    findings = db.scalars(missing_stock_query(q, start, end)).all()
    return templates.TemplateResponse(
        request,
        "missing_stock_report.html",
        {
            "request": request,
            "user": user,
            "findings": findings,
            "summary": {
                "total": len(findings),
                "products": len({finding.product_code for finding in findings if finding.product_code}),
                "audit_batches": len({finding.batch_id for finding in findings}),
                "warehouses": len(
                    {
                        finding.serial.warehouse
                        for finding in findings
                        if finding.serial and finding.serial.warehouse
                    }
                ),
            },
            "q": q,
            "start": start,
            "end": end,
        },
    )


@router.get("/audit-batches/{batch_id}")
def director_audit_batch_detail(request: Request, batch_id: int, db: Session = Depends(get_db)):
    user = require_permission(request, db, "reports_data")
    refresh_expired_audit_assignments(db)
    report = director_audit_batch_report(db, batch_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit batch not found")
    return templates.TemplateResponse(
        request,
        "director_audit_batch.html",
        {
            "request": request,
            "user": user,
            "report": report,
        },
    )


@router.get("/audit-reconciliation.xlsx")
def audit_reconciliation_excel(
    request: Request,
    start: str = "",
    end: str = "",
    fields: str = "",
    db: Session = Depends(get_db),
):
    require_permission(request, db, "reports_data")
    refresh_expired_audit_assignments(db)
    start_at = parse_period_datetime(start, "audit start")
    end_at = parse_period_datetime(end, "audit end", end=True)
    if start_at and end_at and start_at >= end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audit start must be before audit end",
        )
    report = director_audit_reconciliation_report(db, start_at, end_at)
    return Response(
        audit_reconciliation_xlsx(report, fields.split("|")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-audit-reconciliation.xlsx"},
    )


@router.get("/scans.xlsx")
def scans_excel(
    request: Request,
    action: str = "",
    start: str = "",
    end: str = "",
    fields: str = "",
    db: Session = Depends(get_db),
):
    require_permission(request, db, "reports_export")
    scans = db.scalars(scan_query(action, start, end)).all()
    return Response(
        scans_xlsx(scans, fields.split("|")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-scans.xlsx"},
    )


@router.get("/transactions.xlsx")
def transactions_excel(
    request: Request,
    action: str = "",
    q: str = "",
    start: str = "",
    end: str = "",
    fields: str = "",
    db: Session = Depends(get_db),
):
    require_permission(request, db, "reports_export")
    transactions = db.scalars(transaction_query(action, q, start, end)).all()
    return Response(
        transactions_xlsx(transactions, fields.split("|")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-transactions.xlsx"},
    )


@router.get("/missing-stock.xlsx")
def missing_stock_excel(
    request: Request,
    q: str = "",
    start: str = "",
    end: str = "",
    fields: str = "",
    db: Session = Depends(get_db),
):
    require_permission(request, db, "reports_export")
    refresh_expired_audit_assignments(db)
    findings = db.scalars(missing_stock_query(q, start, end)).all()
    return Response(
        missing_stock_xlsx(findings, fields.split("|")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-missing-stock.xlsx"},
    )
