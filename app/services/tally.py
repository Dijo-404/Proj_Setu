from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from app.models import Batch, BatchStatus, BatchType, SyncAttempt, utc_now
from app.services.inventory import update_batch_transaction_references
from app.services.settings import get_all_settings, is_tally_enabled
from app.services.voucher import calculate_voucher_summary


TALLY_XML_SUPPORTED_BATCH_TYPES = {BatchType.PURCHASE.value, BatchType.RECEIVE.value, BatchType.SALE.value}
REQUIRED_TALLY_SETTING_KEYS = {
    "company_name": "company name",
    "sales_voucher_type": "sales voucher type",
    "purchase_voucher_type": "purchase voucher type",
    "sales_ledger_name": "sales ledger",
    "purchase_ledger_name": "purchase ledger",
    "cgst_ledger_name": "CGST ledger",
    "sgst_ledger_name": "SGST ledger",
    "round_off_ledger_name": "round off ledger",
    "default_party_name": "default party",
}


class TallySyncError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True, request_xml: str | None = None, response_xml: str | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.request_xml = request_xml
        self.response_xml = response_xml


@dataclass
class TallyResult:
    request_xml: str
    response_xml: str
    reference: str


def missing_tally_settings(settings: dict[str, str]) -> list[str]:
    return [label for key, label in REQUIRED_TALLY_SETTING_KEYS.items() if not settings.get(key, "").strip()]


def require_tally_settings(settings: dict[str, str]) -> None:
    missing = missing_tally_settings(settings)
    if missing:
        raise TallySyncError(f"Complete Tally settings before generating XML: {', '.join(missing)}", retryable=False)


def _text(parent: ET.Element, tag: str, value: object | None) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = "" if value is None else str(value)
    return child


def _money(value: float | int | Decimal) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_voucher_xml(batch: Batch, settings: dict[str, str]) -> str:
    require_tally_settings(settings)
    batch_type = BatchType(batch.batch_type)
    voucher_type = settings["sales_voucher_type"] if batch_type == BatchType.SALE else settings["purchase_voucher_type"]
    party_name = batch.party_name or settings["default_party_name"]
    date_value = (batch.submitted_at or batch.created_at or datetime.now()).strftime("%Y%m%d")

    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    _text(header, "TALLYREQUEST", "Import Data")
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    request_desc = ET.SubElement(import_data, "REQUESTDESC")
    _text(request_desc, "REPORTNAME", "Vouchers")
    static_variables = ET.SubElement(request_desc, "STATICVARIABLES")
    _text(static_variables, "SVCURRENTCOMPANY", settings["company_name"])
    request_data = ET.SubElement(import_data, "REQUESTDATA")
    message = ET.SubElement(request_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    voucher = ET.SubElement(message, "VOUCHER", {"VCHTYPE": voucher_type, "ACTION": "Create", "OBJVIEW": "Accounting Voucher View"})
    _text(voucher, "DATE", date_value)
    _text(voucher, "VOUCHERTYPENAME", voucher_type)
    _text(voucher, "VOUCHERNUMBER", batch.batch_number)
    _text(voucher, "PARTYLEDGERNAME", party_name)
    _text(voucher, "PERSISTEDVIEW", "Accounting Voucher View")
    _text(voucher, "NARRATION", f"Setu barcode batch {batch.batch_number}")

    summary = calculate_voucher_summary(batch)
    for line in summary.lines:
        inventory = ET.SubElement(voucher, "ALLINVENTORYENTRIES.LIST")
        _text(inventory, "STOCKITEMNAME", line.tally_stock_item_name)
        _text(inventory, "ISDEEMEDPOSITIVE", "Yes" if batch_type == BatchType.SALE else "No")
        _text(inventory, "RATE", f"{_money(line.rate)}/{line.unit}")
        _text(inventory, "AMOUNT", _money(-line.taxable_value if batch_type == BatchType.SALE else line.taxable_value))
        _text(inventory, "ACTUALQTY", f"{line.quantity} {line.unit}")
        _text(inventory, "BILLEDQTY", f"{line.quantity} {line.unit}")

    if summary.taxable_value > 0:
        ledger = settings["sales_ledger_name"] if batch_type == BatchType.SALE else settings["purchase_ledger_name"]
        ledger_entry = ET.SubElement(voucher, "LEDGERENTRIES.LIST")
        _text(ledger_entry, "LEDGERNAME", ledger)
        _text(ledger_entry, "ISDEEMEDPOSITIVE", "No" if batch_type == BatchType.SALE else "Yes")
        _text(ledger_entry, "AMOUNT", _money(summary.taxable_value if batch_type == BatchType.SALE else -summary.taxable_value))

    return ET.tostring(envelope, encoding="unicode")


def post_to_tally(xml: str, settings: dict[str, str]) -> TallyResult:
    url = f"http://{settings['tally_host']}:{settings['tally_port']}"
    request = Request(url, data=xml.encode("utf-8"), headers={"Content-Type": "text/xml"}, method="POST")
    try:
        with urlopen(request, timeout=5) as response:
            response_xml = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise TallySyncError("Tally connection failed", retryable=True, request_xml=xml) from exc

    try:
        root = ET.fromstring(response_xml)
    except ET.ParseError as exc:
        raise TallySyncError("Tally returned unreadable XML", retryable=False, request_xml=xml, response_xml=response_xml) from exc

    errors = [node.text for node in root.iter() if node.tag.upper().endswith("LINEERROR") and node.text]
    if errors:
        raise TallySyncError("; ".join(errors), retryable=False, request_xml=xml, response_xml=response_xml)

    created = next((node.text for node in root.iter() if node.tag.upper().endswith("CREATED")), None)
    altered = next((node.text for node in root.iter() if node.tag.upper().endswith("ALTERED")), None)
    reference = f"CREATED={created or 0}; ALTERED={altered or 0}"
    return TallyResult(request_xml=xml, response_xml=response_xml, reference=reference)


def sync_batch(db: Session, batch: Batch) -> None:
    is_retry = batch.status in {BatchStatus.PENDING_SYNC.value, BatchStatus.FAILED.value}
    if is_retry:
        batch.retry_count = (batch.retry_count or 0) + 1
        batch.last_retry_at = utc_now()
    if BatchType(batch.batch_type) in {BatchType.AUDIT, BatchType.QR_ASSIGNMENT}:
        batch.status = BatchStatus.CLOSED.value
        batch.synced_at = utc_now()
        db.commit()
        return
    settings = get_all_settings(db)
    if batch.batch_type not in TALLY_XML_SUPPORTED_BATCH_TYPES:
        batch.status = BatchStatus.PENDING_SYNC.value
        batch.last_error = f"Tally XML is not configured for {batch.batch_type}"
        db.add(SyncAttempt(batch_id=batch.id, status=BatchStatus.PENDING_SYNC.value, error=batch.last_error))
        db.commit()
        return
    try:
        xml = build_voucher_xml(batch, settings)
    except TallySyncError as exc:
        batch.status = BatchStatus.PENDING_SYNC.value
        batch.last_error = str(exc)
        db.add(SyncAttempt(batch_id=batch.id, status=BatchStatus.PENDING_SYNC.value, error=batch.last_error))
        db.commit()
        return
    if not is_tally_enabled(db):
        batch.status = BatchStatus.PENDING_SYNC.value
        batch.last_error = "Tally sync is disabled in settings"
        db.add(SyncAttempt(batch_id=batch.id, status=BatchStatus.PENDING_SYNC.value, request_xml=xml, error=batch.last_error))
        db.commit()
        return
    try:
        result = post_to_tally(xml, settings)
    except TallySyncError as exc:
        batch.status = BatchStatus.PENDING_SYNC.value if exc.retryable else BatchStatus.FAILED.value
        batch.last_error = str(exc)
        db.add(
            SyncAttempt(
                batch_id=batch.id,
                status=batch.status,
                request_xml=exc.request_xml,
                response_xml=exc.response_xml,
                error=str(exc),
            )
        )
        db.commit()
        return
    batch.status = BatchStatus.SYNCED.value
    batch.tally_reference = result.reference
    batch.last_error = None
    batch.synced_at = utc_now()
    update_batch_transaction_references(db, batch)
    db.add(
        SyncAttempt(
            batch_id=batch.id,
            status=BatchStatus.SYNCED.value,
            request_xml=result.request_xml,
            response_xml=result.response_xml,
        )
    )
    db.commit()
