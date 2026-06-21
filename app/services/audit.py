from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditFinding, Batch, BatchType, Serial, SerialStatus


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
