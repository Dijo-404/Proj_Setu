from collections import Counter
from datetime import datetime, timedelta, timezone
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_permission
from app.database import get_db
from app.models import Batch, InventoryTransaction, Product, ScanLog, TransactionType
from app.services.charts import bar_chart, donut_chart
from app.services.expiry import expiry_summary
from app.services.exports import safe_row, scans_xlsx, transactions_xlsx
from app.services.log_fields import barcode_sold_by, invoice_created_by, product_audited_by
from app.templates import templates

router = APIRouter(prefix="/reports")


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


@router.get("")
def reports(request: Request, action: str = "", q: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    user = require_permission(request, db, "reports_data")
    scans = db.scalars(scan_query(action, start, end)).all()
    transactions = db.scalars(transaction_query(action, q, start, end)).all()
    transaction_counts = Counter(txn.transaction_type for txn in transactions)
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
            "pending": pending,
            "transaction_chart": bar_chart(transaction_counts.items()),
            "scan_status_chart": donut_chart(scan_status_counts.items()),
            "expiry": expiry_summary(db),
            "action": action,
            "q": q,
            "start": start,
            "end": end,
            "transaction_types": [item.value for item in TransactionType],
            "invoice_created_by": invoice_created_by,
            "barcode_sold_by": barcode_sold_by,
            "product_audited_by": product_audited_by,
        },
    )


@router.get("/scans.csv")
def scans_csv(request: Request, action: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_permission(request, db, "reports_export")
    scans = db.scalars(scan_query(action, start, end)).all()
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Date", "User", "Action", "Serial", "Status", "Batch", "Message", "Tally Reference"])
    for scan in scans:
        writer.writerow(
            safe_row(
                [
                    scan.created_at.isoformat(),
                    scan.user.username,
                    scan.action,
                    scan.serial_number_raw,
                    scan.status,
                    scan.batch.batch_number if scan.batch else "",
                    scan.message or "",
                    scan.tally_reference or "",
                ]
            )
        )
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=setu-scans.csv"},
    )


@router.get("/scans.xlsx")
def scans_excel(request: Request, action: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_permission(request, db, "reports_export")
    scans = db.scalars(scan_query(action, start, end)).all()
    return Response(
        scans_xlsx(scans),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-scans.xlsx"},
    )


@router.get("/transactions.csv")
def transactions_csv(request: Request, action: str = "", q: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_permission(request, db, "reports_export")
    transactions = db.scalars(transaction_query(action, q, start, end)).all()
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "Date",
            "User",
            "Type",
            "Serial",
            "Product Code",
            "Product Name",
            "Invoice Created By",
            "Barcode Sold By",
            "Product Audited By",
            "From Status",
            "To Status",
            "Reason",
            "Batch/Reference",
            "Tally Reference",
            "Notes",
        ]
    )
    for txn in transactions:
        writer.writerow(
            safe_row(
                [
                    txn.created_at.isoformat(),
                    txn.user.username,
                    txn.transaction_type,
                    txn.serial_number or "",
                    txn.product.product_code if txn.product else "",
                    txn.product.product_name if txn.product else "",
                    invoice_created_by(txn),
                    barcode_sold_by(txn),
                    product_audited_by(txn),
                    txn.status_from or "",
                    txn.status_to or "",
                    txn.reason_code or "",
                    txn.reference_number or "",
                    txn.tally_reference or "",
                    txn.notes or "",
                ]
            )
        )
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=setu-transactions.csv"},
    )


@router.get("/transactions.xlsx")
def transactions_excel(request: Request, action: str = "", q: str = "", start: str = "", end: str = "", db: Session = Depends(get_db)):
    require_permission(request, db, "reports_export")
    transactions = db.scalars(transaction_query(action, q, start, end)).all()
    return Response(
        transactions_xlsx(transactions),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setu-transactions.xlsx"},
    )
