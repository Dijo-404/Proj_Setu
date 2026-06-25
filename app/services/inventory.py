from collections import defaultdict
from datetime import date, datetime, timezone
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchItem,
    BatchStatus,
    BatchType,
    InventoryTransaction,
    Product,
    ScanLog,
    Serial,
    SerialStatus,
    TransactionType,
    User,
)
from app.services.expiry import validate_fefo_scan


class InventoryError(ValueError):
    pass


def normalize_serial(serial_number: str) -> str:
    return serial_number.strip().upper()


def next_batch_number(db: Session, batch_type: BatchType) -> str:
    prefix = {
        BatchType.PURCHASE: "PUR",
        BatchType.RECEIVE: "RCV",
        BatchType.SALE: "SAL",
        BatchType.AUDIT: "AUD",
        BatchType.PURCHASE_RETURN: "PRT",
        BatchType.SALES_RETURN: "SRT",
        BatchType.ISSUE: "ISS",
        BatchType.QR_ASSIGNMENT: "ASN",
    }[batch_type]
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    count = db.scalar(select(func.count(Batch.id)).where(Batch.batch_number.like(f"{prefix}-{today}-%"))) or 0
    return f"{prefix}-{today}-{count + 1:04d}"


def create_batch(db: Session, user: User, batch_type: BatchType, party_name: str | None, notes: str | None, reason_code: str | None = None) -> Batch:
    for attempt in range(5):
        batch = Batch(
            batch_number=next_batch_number(db, batch_type),
            batch_type=batch_type.value,
            party_name=party_name.strip() if party_name else None,
            reason_code=reason_code.strip().upper() if reason_code else None,
            user_id=user.id,
            notes=notes.strip() if notes else None,
        )
        db.add(batch)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if attempt == 4:
                raise InventoryError("Could not allocate a unique batch number; try again") from exc
            continue
        db.refresh(batch)
        return batch
    raise InventoryError("Could not allocate a unique batch number; try again")


def transaction_type_for_batch(batch_type: BatchType) -> TransactionType:
    if batch_type in {BatchType.PURCHASE, BatchType.RECEIVE}:
        return TransactionType.PURCHASE
    if batch_type == BatchType.SALE:
        return TransactionType.SALE
    if batch_type == BatchType.SALES_RETURN:
        return TransactionType.SALES_RETURN
    if batch_type == BatchType.PURCHASE_RETURN:
        return TransactionType.PURCHASE_RETURN
    if batch_type == BatchType.ISSUE:
        return TransactionType.ISSUE
    if batch_type == BatchType.AUDIT:
        return TransactionType.AUDIT
    if batch_type == BatchType.QR_ASSIGNMENT:
        return TransactionType.QR_ASSIGNMENT
    raise InventoryError(f"{batch_type.value} is not a supported transaction type")


def log_inventory_transaction(
    db: Session,
    user: User,
    transaction_type: TransactionType,
    serial: Serial | None = None,
    product: Product | None = None,
    batch: Batch | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    reason_code: str | None = None,
    tally_reference: str | None = None,
    reference_number: str | None = None,
    notes: str | None = None,
) -> InventoryTransaction:
    row = InventoryTransaction(
        transaction_type=transaction_type.value,
        serial_id=serial.id if serial else None,
        product_id=(product.id if product else serial.product_id if serial else None),
        batch_id=batch.id if batch else None,
        user_id=user.id,
        serial_number=serial.serial_number if serial else None,
        status_from=status_from,
        status_to=status_to,
        reason_code=reason_code.strip().upper() if reason_code else None,
        tally_reference=tally_reference,
        reference_number=reference_number or (batch.batch_number if batch else None),
        notes=notes.strip() if notes else None,
    )
    db.add(row)
    return row


def serial_allowed_for_batch(serial: Serial, batch_type: BatchType) -> None:
    status = SerialStatus(serial.status)
    if not serial.active or status in {SerialStatus.REPLACED, SerialStatus.INVALID}:
        raise InventoryError(f"{serial.serial_number} is inactive")
    if batch_type in {BatchType.PURCHASE, BatchType.RECEIVE}:
        if status not in {SerialStatus.GENERATED, SerialStatus.PURCHASE_RETURN}:
            raise InventoryError(f"{serial.serial_number} cannot be purchased from {serial.status}")
    elif batch_type == BatchType.SALE:
        if status not in {SerialStatus.IN_STOCK, SerialStatus.RETURNED}:
            raise InventoryError(f"{serial.serial_number} is not available for sale")
    elif batch_type == BatchType.AUDIT:
        return
    elif batch_type == BatchType.SALES_RETURN:
        if status != SerialStatus.SOLD:
            raise InventoryError(f"{serial.serial_number} is not sold")
    elif batch_type == BatchType.PURCHASE_RETURN:
        if status not in {SerialStatus.IN_STOCK, SerialStatus.RETURNED}:
            raise InventoryError(f"{serial.serial_number} is not available for purchase return")
    elif batch_type == BatchType.ISSUE:
        if status != SerialStatus.IN_STOCK:
            raise InventoryError(f"{serial.serial_number} is not available for issue")
    elif batch_type == BatchType.QR_ASSIGNMENT:
        if status != SerialStatus.GENERATED:
            raise InventoryError(f"{serial.serial_number} is already assigned")
    else:
        raise InventoryError(f"{batch_type.value} is not supported")


def add_serial_to_batch(db: Session, batch: Batch, user: User, serial_number: str) -> BatchItem:
    if batch.status != BatchStatus.DRAFT.value:
        raise InventoryError("This batch is already submitted")
    serial_number = normalize_serial(serial_number)
    serial = db.scalar(select(Serial).where(Serial.serial_number == serial_number))
    if not serial:
        db.add(
            ScanLog(
                serial_number_raw=serial_number,
                user_id=user.id,
                action=batch.batch_type,
                batch_id=batch.id,
                status="REJECTED",
                message="Serial number not found",
            )
        )
        db.commit()
        raise InventoryError("Serial number not found")
    serial_allowed_for_batch(serial, BatchType(batch.batch_type))
    fefo_error = validate_fefo_scan(db, batch, serial)
    if fefo_error:
        raise InventoryError(fefo_error)
    existing = db.scalar(
        select(BatchItem).where(BatchItem.batch_id == batch.id, BatchItem.serial_id == serial.id)
    )
    if existing:
        raise InventoryError("Already scanned in this batch")
    item = BatchItem(batch_id=batch.id, serial_id=serial.id)
    db.add(item)
    db.add(
        ScanLog(
            serial_id=serial.id,
            serial_number_raw=serial.serial_number,
            user_id=user.id,
            action=batch.batch_type,
            batch_id=batch.id,
            status="SCANNED",
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InventoryError("Already scanned in this batch") from exc
    db.refresh(item)
    return item


def remove_batch_item(db: Session, batch: Batch, item_id: int) -> None:
    if batch.status != BatchStatus.DRAFT.value:
        raise InventoryError("Submitted batches cannot be edited")
    item = db.get(BatchItem, item_id)
    if not item or item.batch_id != batch.id:
        raise InventoryError("Scan not found")
    db.delete(item)
    db.commit()


def apply_batch_statuses(db: Session, batch: Batch, user: User) -> None:
    batch_type = BatchType(batch.batch_type)
    if not batch.items:
        raise InventoryError("Scan at least one serial before submitting")
    for item in batch.items:
        serial_allowed_for_batch(item.serial, batch_type)
    for item in batch.items:
        previous_status = item.serial.status
        scan_status = "SUBMITTED"
        if batch_type == BatchType.RECEIVE:
            item.serial.status = SerialStatus.IN_STOCK.value
            scan_status = SerialStatus.PURCHASED.value
        elif batch_type == BatchType.PURCHASE:
            item.serial.status = SerialStatus.IN_STOCK.value
            scan_status = SerialStatus.PURCHASED.value
        elif batch_type == BatchType.SALE:
            item.serial.status = SerialStatus.SOLD.value
            scan_status = SerialStatus.SOLD.value
        elif batch_type == BatchType.SALES_RETURN:
            item.serial.status = SerialStatus.DAMAGED.value if batch.reason_code in {"DAMAGED", "EXPIRED"} else SerialStatus.IN_STOCK.value
            scan_status = SerialStatus.DAMAGED.value if batch.reason_code in {"DAMAGED", "EXPIRED"} else SerialStatus.RETURNED.value
        elif batch_type == BatchType.PURCHASE_RETURN:
            item.serial.status = SerialStatus.PURCHASE_RETURN.value
            scan_status = SerialStatus.PURCHASE_RETURN.value
        elif batch_type == BatchType.ISSUE:
            item.serial.status = SerialStatus.ISSUED.value
            scan_status = SerialStatus.ISSUED.value
        elif batch_type == BatchType.AUDIT:
            scan_status = SerialStatus.AUDITED.value
        db.add(
            ScanLog(
                serial_id=item.serial.id,
                serial_number_raw=item.serial.serial_number,
                user_id=user.id,
                action=batch.batch_type,
                batch_id=batch.id,
                status=scan_status,
                tally_reference=batch.tally_reference,
            )
        )
        log_inventory_transaction(
            db,
            user,
            transaction_type_for_batch(batch_type),
            serial=item.serial,
            batch=batch,
            status_from=previous_status,
            status_to=item.serial.status,
            reason_code=batch.reason_code,
            tally_reference=batch.tally_reference,
            notes=batch.notes,
        )
    batch.status = BatchStatus.SUBMITTED.value
    batch.submitted_at = datetime.now(timezone.utc)


def update_batch_transaction_references(db: Session, batch: Batch) -> None:
    if not batch.tally_reference:
        return
    rows = db.scalars(select(InventoryTransaction).where(InventoryTransaction.batch_id == batch.id)).all()
    for row in rows:
        row.tally_reference = batch.tally_reference


def group_batch_items(batch: Batch) -> list[dict[str, object]]:
    grouped: dict[tuple[int, float], dict[str, object]] = {}
    for item in batch.items:
        product = item.serial.product
        rate = item.rate if item.rate is not None else product.default_rate
        row = grouped.setdefault(
            (product.id, float(rate or 0)),
            {
                "product": product,
                "quantity": 0,
                "serials": [],
                "rate": rate,
            },
        )
        row["quantity"] = int(row["quantity"]) + item.quantity
        row["serials"].append(item.serial.serial_number)
    return list(grouped.values())


def update_batch_item_rate(db: Session, batch: Batch, item_id: int, rate: float) -> None:
    if batch.status != BatchStatus.DRAFT.value:
        raise InventoryError("Submitted batches cannot be edited")
    if rate < 0:
        raise InventoryError("Rate cannot be negative")
    item = db.get(BatchItem, item_id)
    if not item or item.batch_id != batch.id:
        raise InventoryError("Scan not found")
    item.rate = rate
    db.commit()


def update_product_rate_in_batch(db: Session, batch: Batch, product_id: int, rate: float) -> None:
    if batch.status != BatchStatus.DRAFT.value:
        raise InventoryError("Submitted batches cannot be edited")
    if rate < 0:
        raise InventoryError("Rate cannot be negative")
    updated = False
    for item in batch.items:
        if item.serial.product_id == product_id:
            item.rate = rate
            updated = True
    if not updated:
        raise InventoryError("Product not found in batch")
    db.commit()


def generate_serials(
    db: Session,
    product: Product,
    quantity: int,
    prefix: str | None = None,
    initial_status: SerialStatus = SerialStatus.GENERATED,
    product_batch_number: str | None = None,
    mfg_date: date | None = None,
    expiry_date: date | None = None,
    warehouse: str | None = None,
) -> list[Serial]:
    if quantity < 1:
        raise InventoryError("Quantity must be at least 1")
    if quantity > 5000:
        raise InventoryError("Generate 5000 labels or fewer at a time")
    serial_prefix = normalize_serial(prefix or product.product_code)
    pattern = re.compile(rf"^{re.escape(serial_prefix)}-(\d+)$")
    for attempt in range(5):
        max_number = 0
        rows = db.scalars(select(Serial.serial_number).where(Serial.serial_number.like(f"{serial_prefix}-%"))).all()
        for serial_number in rows:
            match = pattern.match(serial_number)
            if match:
                max_number = max(max_number, int(match.group(1)))
        created = []
        for offset in range(1, quantity + 1):
            serial = Serial(
                serial_number=f"{serial_prefix}-{max_number + offset:06d}",
                product_id=product.id,
                status=initial_status.value,
                product_batch_number=product_batch_number.strip().upper() if product_batch_number else None,
                mfg_date=mfg_date,
                expiry_date=expiry_date,
                warehouse=warehouse.strip().upper() if warehouse else None,
            )
            db.add(serial)
            created.append(serial)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if attempt == 4:
                raise InventoryError("Could not allocate unique serial numbers; try again") from exc
            continue
        for serial in created:
            db.refresh(serial)
        return created
    raise InventoryError("Could not allocate unique serial numbers; try again")


def dashboard_counts(db: Session) -> dict[str, int]:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {
        "products": db.scalar(select(func.count(Product.id))) or 0,
        "serials": db.scalar(select(func.count(Serial.id))) or 0,
        "in_stock": db.scalar(select(func.count(Serial.id)).where(Serial.status == SerialStatus.IN_STOCK.value)) or 0,
        "sold": db.scalar(select(func.count(Serial.id)).where(Serial.status == SerialStatus.SOLD.value)) or 0,
        "pending_sync": db.scalar(select(func.count(Batch.id)).where(Batch.status == BatchStatus.PENDING_SYNC.value)) or 0,
        "failed": db.scalar(select(func.count(Batch.id)).where(Batch.status == BatchStatus.FAILED.value)) or 0,
        "today_scans": db.scalar(select(func.count(ScanLog.id)).where(ScanLog.created_at >= today_start)) or 0,
    }
    return counts


def status_summary(db: Session) -> dict[str, int]:
    rows = db.execute(select(Serial.status, func.count(Serial.id)).group_by(Serial.status)).all()
    return defaultdict(int, {status: count for status, count in rows})
