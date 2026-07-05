from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditFinding, Batch, BatchType, Product, Serial
from app.services.expiry import STOCK_STATUSES, expiry_summary


def audit_time(batch: Batch) -> datetime | None:
    return batch.submitted_at or batch.created_at


def _audit_order():
    return desc(func.coalesce(Batch.submitted_at, Batch.created_at))


def director_audit_batch_rows(db: Session, limit: int = 30) -> list[dict[str, object]]:
    batches = db.scalars(
        select(Batch)
        .where(Batch.batch_type == BatchType.AUDIT.value)
        .options(selectinload(Batch.user), selectinload(Batch.audit_findings))
        .order_by(_audit_order(), desc(Batch.id))
        .limit(limit)
    ).all()

    rows: list[dict[str, object]] = []
    for batch in batches:
        counts = Counter(finding.finding_type for finding in batch.audit_findings)
        product_codes = {
            finding.product_code
            for finding in batch.audit_findings
            if finding.product_code
        }
        rows.append(
            {
                "id": batch.id,
                "batch_number": batch.batch_number,
                "audited_by": batch.user.username if batch.user else "-",
                "audit_at": audit_time(batch),
                "products": len(product_codes),
                "verified": counts["VERIFIED"],
                "pending": counts["PENDING"],
                "missing": counts["MISSING"],
                "extra": counts["EXTRA"],
                "total": sum(counts.values()),
            }
        )
    return rows


def director_audit_reconciliation_report(
    db: Session,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    audit_moment = func.coalesce(Batch.submitted_at, Batch.created_at)
    query = (
        select(Batch)
        .where(Batch.batch_type == BatchType.AUDIT.value)
        .options(selectinload(Batch.user), selectinload(Batch.audit_findings))
        .order_by(desc(audit_moment), desc(Batch.id))
    )
    if start_at:
        query = query.where(audit_moment >= start_at)
    if end_at:
        query = query.where(audit_moment < end_at)
    if limit:
        query = query.limit(limit)
    batches = db.scalars(query).all()

    totals = Counter()
    product_rows: dict[tuple[str, str], dict[str, object]] = {}
    finding_rows: list[dict[str, object]] = []
    batch_rows: list[dict[str, object]] = []

    for batch in batches:
        batch_counts = Counter(finding.finding_type for finding in batch.audit_findings)
        batch_products = {
            finding.product_code
            for finding in batch.audit_findings
            if finding.product_code
        }
        batch_rows.append(
            {
                "id": batch.id,
                "batch_number": batch.batch_number,
                "audited_by": batch.user.username if batch.user else "-",
                "audit_at": audit_time(batch),
                "products": len(batch_products),
                "verified": batch_counts["VERIFIED"],
                "pending": batch_counts["PENDING"],
                "missing": batch_counts["MISSING"],
                "extra": batch_counts["EXTRA"],
                "total": sum(batch_counts.values()),
            }
        )

        for finding in batch.audit_findings:
            totals[finding.finding_type] += 1
            key = (finding.product_code or "-", finding.product_name or "-")
            product_row = product_rows.setdefault(
                key,
                {
                    "product_code": key[0],
                    "product_name": key[1],
                    "audit_batches": set(),
                    "verified": 0,
                    "pending": 0,
                    "missing": 0,
                    "extra": 0,
                    "total": 0,
                },
            )
            product_row["audit_batches"].add(batch.batch_number)  # type: ignore[union-attr]
            product_row["total"] = int(product_row["total"]) + 1
            if finding.finding_type == "VERIFIED":
                product_row["verified"] = int(product_row["verified"]) + 1
            elif finding.finding_type == "PENDING":
                product_row["pending"] = int(product_row["pending"]) + 1
            elif finding.finding_type == "MISSING":
                product_row["missing"] = int(product_row["missing"]) + 1
            elif finding.finding_type == "EXTRA":
                product_row["extra"] = int(product_row["extra"]) + 1

            finding_rows.append(
                {
                    "audit_at": audit_time(batch),
                    "batch_number": batch.batch_number,
                    "audited_by": batch.user.username if batch.user else "-",
                    "serial_number": finding.serial_number,
                    "product_code": finding.product_code or "-",
                    "product_name": finding.product_name or "-",
                    "type": finding.finding_type,
                    "expected_status": finding.expected_status or "-",
                    "scanned_status": finding.scanned_status or "-",
                }
            )

    normalized_product_rows = []
    for row in product_rows.values():
        batches_for_product = sorted(row["audit_batches"])  # type: ignore[arg-type]
        normalized_product_rows.append(
            {
                **row,
                "audit_batches": ", ".join(batches_for_product),
                "audit_batch_count": len(batches_for_product),
            }
        )

    return {
        "start_at": start_at,
        "end_at": end_at,
        "batch_rows": batch_rows,
        "product_rows": sorted(
            normalized_product_rows,
            key=lambda row: (-int(row["missing"]), -int(row["extra"]), str(row["product_name"])),
        ),
        "finding_rows": sorted(
            finding_rows,
            key=lambda row: (
                row["audit_at"] or datetime.min,
                str(row["batch_number"]),
                str(row["product_name"]),
                str(row["serial_number"]),
            ),
        ),
        "audit_batch_count": len(batches),
        "verified": totals["VERIFIED"],
        "pending": totals["PENDING"],
        "missing": totals["MISSING"],
        "extra": totals["EXTRA"],
        "total": sum(totals.values()),
    }


def director_product_stock_rows(db: Session, limit: int = 40) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            Product.product_code,
            Product.product_name,
            func.count(Serial.id).label("stock"),
            func.min(Serial.expiry_date).label("nearest_expiry"),
        )
        .outerjoin(
            Serial,
            and_(
                Serial.product_id == Product.id,
                Serial.active == True,
                Serial.status.in_(STOCK_STATUSES),
            ),
        )
        .where(Product.active == True)
        .group_by(Product.id, Product.product_code, Product.product_name)
        .order_by(desc(func.count(Serial.id)), Product.product_name)
        .limit(limit)
    ).all()
    return [
        {
            "product_code": product_code,
            "product_name": product_name,
            "stock": stock or 0,
            "nearest_expiry": nearest_expiry,
        }
        for product_code, product_name, stock, nearest_expiry in rows
    ]


def director_product_totals(db: Session) -> dict[str, int]:
    total_products = db.scalar(select(func.count(Product.id)).where(Product.active == True)) or 0
    total_stock = db.scalar(
        select(func.count(Serial.id)).where(Serial.active == True, Serial.status.in_(STOCK_STATUSES))
    ) or 0
    products_with_stock = db.scalar(
        select(func.count(func.distinct(Serial.product_id))).where(
            Serial.active == True,
            Serial.status.in_(STOCK_STATUSES),
        )
    ) or 0
    return {
        "total_products": int(total_products),
        "total_stock": int(total_stock),
        "products_with_stock": int(products_with_stock),
    }


def director_report(
    db: Session,
    audit_start_at: datetime | None = None,
    audit_end_at: datetime | None = None,
) -> dict[str, object]:
    audit_batches = director_audit_batch_rows(db)
    latest_audit = audit_batches[0] if audit_batches else None
    audit_batch_count = db.scalar(
        select(func.count(Batch.id)).where(Batch.batch_type == BatchType.AUDIT.value)
    ) or 0
    expiry = expiry_summary(db)
    sleeping_stock = expiry["sleeping_stock"]
    dead_stock_rows = [
        row for row in sleeping_stock if isinstance(row, dict) and row.get("status") == "Dead Stock"
    ]
    products = director_product_totals(db)
    return {
        "audit_batches": audit_batches,
        "audit_batch_count": int(audit_batch_count),
        "latest_audit": latest_audit,
        "latest_missing": int(latest_audit["missing"]) if latest_audit else 0,
        "latest_extra": int(latest_audit["extra"]) if latest_audit else 0,
        "expiry": expiry,
        "dead_stock_rows": dead_stock_rows,
        "product_rows": director_product_stock_rows(db),
        "products": products,
        "reconciliation": director_audit_reconciliation_report(db, audit_start_at, audit_end_at),
    }


def director_audit_batch_report(db: Session, batch_id: int) -> dict[str, object] | None:
    batch = db.scalar(
        select(Batch)
        .where(Batch.id == batch_id, Batch.batch_type == BatchType.AUDIT.value)
        .options(
            selectinload(Batch.user),
            selectinload(Batch.audit_findings).selectinload(AuditFinding.serial),
        )
    )
    if not batch:
        return None

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for finding in batch.audit_findings:
        key = (finding.product_code or "-", finding.product_name or "-")
        row = grouped.setdefault(
            key,
            {
                "product_code": key[0],
                "product_name": key[1],
                "verified": 0,
                "pending": 0,
                "missing": 0,
                "extra": 0,
                "total": 0,
            },
        )
        row["total"] = int(row["total"]) + 1
        if finding.finding_type == "VERIFIED":
            row["verified"] = int(row["verified"]) + 1
        elif finding.finding_type == "PENDING":
            row["pending"] = int(row["pending"]) + 1
        elif finding.finding_type == "MISSING":
            row["missing"] = int(row["missing"]) + 1
        elif finding.finding_type == "EXTRA":
            row["extra"] = int(row["extra"]) + 1

    product_rows = sorted(
        (
            row
            for row in grouped.values()
            if int(row["pending"]) or int(row["missing"]) or int(row["extra"])
        ),
        key=lambda row: (-int(row["missing"]), -int(row["extra"]), str(row["product_name"])),
    )
    counts = Counter(finding.finding_type for finding in batch.audit_findings)
    finding_rows = sorted(
        (
            {
                "serial_number": finding.serial_number,
                "product_code": finding.product_code or "-",
                "product_name": finding.product_name or "-",
                "type": finding.finding_type,
                "expected_status": finding.expected_status or "-",
                "scanned_status": finding.scanned_status or "-",
            }
            for finding in batch.audit_findings
            if finding.finding_type in {"PENDING", "MISSING", "EXTRA"}
        ),
        key=lambda row: (str(row["type"]), str(row["product_name"]), str(row["serial_number"])),
    )
    return {
        "batch": batch,
        "audit_at": audit_time(batch),
        "audited_by": batch.user.username if batch.user else "-",
        "product_rows": product_rows,
        "finding_rows": finding_rows,
        "verified": counts["VERIFIED"],
        "pending": counts["PENDING"],
        "missing": counts["MISSING"],
        "extra": counts["EXTRA"],
        "total": sum(counts.values()),
    }
