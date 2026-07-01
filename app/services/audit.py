from collections import Counter
from dataclasses import dataclass

from sqlalchemy import and_, delete, desc, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import AuditFinding, Batch, BatchType, Serial, SerialStatus
from app.services.expiry import STOCK_STATUSES


@dataclass(frozen=True)
class AuditSummary:
    verified: int
    missing: int
    extra: int
    total: int


def reconcile_audit_batch(db: Session, batch: Batch) -> AuditSummary:
    if batch.batch_type != BatchType.AUDIT.value:
        return AuditSummary(0, 0, 0, 0)

    db.execute(delete(AuditFinding).where(AuditFinding.batch_id == batch.id))

    scanned = {item.serial_id: item.serial for item in batch.items}
    expected = db.scalars(select(Serial).where(Serial.status == SerialStatus.IN_STOCK.value, Serial.active == True)).all()
    expected_ids = {serial.id for serial in expected}
    findings = []

    for serial in expected:
        if serial.id in scanned:
            findings.append(make_finding(batch, serial, "VERIFIED", SerialStatus.IN_STOCK.value, serial.status))
        else:
            findings.append(make_finding(batch, serial, "MISSING", SerialStatus.IN_STOCK.value, None))

    for serial_id, serial in scanned.items():
        if serial_id not in expected_ids:
            findings.append(make_finding(batch, serial, "EXTRA", SerialStatus.IN_STOCK.value, serial.status))

    db.add_all(findings)
    db.flush()
    counts = Counter(finding.finding_type for finding in findings)
    return AuditSummary(
        verified=counts["VERIFIED"],
        missing=counts["MISSING"],
        extra=counts["EXTRA"],
        total=len(findings),
    )


def make_finding(batch: Batch, serial: Serial, finding_type: str, expected_status: str | None, scanned_status: str | None) -> AuditFinding:
    return AuditFinding(
        batch_id=batch.id,
        serial_id=serial.id,
        serial_number=serial.serial_number,
        product_code=serial.product.product_code,
        product_name=serial.product.product_name,
        finding_type=finding_type,
        expected_status=expected_status,
        scanned_status=scanned_status,
    )


def summarize_audit_findings(batch: Batch) -> AuditSummary:
    counts = Counter(finding.finding_type for finding in batch.audit_findings)
    return AuditSummary(
        verified=counts["VERIFIED"],
        missing=counts["MISSING"],
        extra=counts["EXTRA"],
        total=len(batch.audit_findings),
    )


def current_missing_stock_findings_query():
    """Return missing findings that have not been resolved by a newer audit scan."""
    newer_finding = aliased(AuditFinding)
    newer_for_same_serial = (
        select(newer_finding.id)
        .where(
            newer_finding.serial_id == AuditFinding.serial_id,
            or_(
                newer_finding.created_at > AuditFinding.created_at,
                and_(
                    newer_finding.created_at == AuditFinding.created_at,
                    newer_finding.id > AuditFinding.id,
                ),
            ),
        )
        .exists()
    )
    return (
        select(AuditFinding)
        .join(Serial, AuditFinding.serial_id == Serial.id)
        .where(
            AuditFinding.finding_type == "MISSING",
            AuditFinding.serial_id.is_not(None),
            Serial.active == True,
            Serial.status.in_(STOCK_STATUSES),
            ~newer_for_same_serial,
        )
        .order_by(desc(AuditFinding.created_at), desc(AuditFinding.id))
    )
