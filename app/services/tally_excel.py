from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.models import Batch, BatchItem, BatchStatus, BatchType, ScanLog, Serial, User
from app.services.assignment import AssignmentLine, MAX_ASSIGNMENT_QUANTITY, parse_bulk_assignment_xlsx
from app.services.expiry import fefo_available_statuses, fefo_candidate_serials
from app.services.exports import safe_row
from app.services.inventory import InventoryError
from app.services.voucher import calculate_voucher_summary


MAX_TALLY_EXCEL_UPLOAD_BYTES = 5 * 1024 * 1024
TALLY_EXCEL_IMPORT_BATCH_TYPES = {
    BatchType.SALE.value,
    BatchType.ISSUE.value,
    BatchType.PURCHASE_RETURN.value,
}
TALLY_EXCEL_EXPORT_BATCH_TYPES = {
    BatchType.PURCHASE.value,
    BatchType.RECEIVE.value,
    BatchType.SALE.value,
    BatchType.SALES_RETURN.value,
    BatchType.PURCHASE_RETURN.value,
    BatchType.ISSUE.value,
}
TALLY_EXCEL_HEADERS = [
    "Sl",
    "Description of Goods",
    "Product Code",
    "Tally Stock Item",
    "HSN/SAC",
    "Quantity",
    "Unit",
    "Rate",
    "Discount %",
    "GST %",
    "CGST %",
    "SGST %",
    "IGST %",
    "Taxable Value",
    "CGST Amount",
    "SGST Amount",
    "IGST Amount",
    "Amount",
]


@dataclass(frozen=True)
class TallyExcelImportResult:
    product_lines: int
    quantity: int


def batch_tally_xlsx(batch: Batch) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tally Voucher"
    summary = calculate_voucher_summary(batch)

    sheet.append(["Voucher Type", batch.batch_type])
    sheet.append(["Voucher Number", batch.batch_number])
    sheet.append(["Party Ledger", batch.party_name or ""])
    sheet.append(["Date", (batch.submitted_at or batch.created_at).date().isoformat()])
    sheet.append([])
    sheet.append(TALLY_EXCEL_HEADERS)

    total_quantity = 0
    for index, line in enumerate(summary.lines, start=1):
        total_quantity += line.quantity
        sheet.append(
            safe_row(
                [
                    index,
                    line.tally_stock_item_name or line.product_name,
                    line.product_code,
                    line.tally_stock_item_name,
                    line.hsn,
                    line.quantity,
                    line.unit,
                    float(line.rate),
                    float(line.discount_rate),
                    float(line.gst_rate),
                    float(line.cgst_rate),
                    float(line.sgst_rate),
                    float(line.igst_rate),
                    float(line.taxable_value),
                    float(line.cgst_amount),
                    float(line.sgst_amount),
                    float(line.igst_amount),
                    float(line.line_total),
                ]
            )
        )

    sheet.append(
        safe_row(
            [
                "",
                "Total",
                "",
                "",
                "",
                total_quantity,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                float(summary.taxable_value),
                float(summary.cgst_amount),
                float(summary.sgst_amount),
                float(summary.igst_amount),
                float(summary.final_value),
            ]
        )
    )
    sheet.freeze_panes = "A7"
    sheet.auto_filter.ref = f"A6:R{max(sheet.max_row, 6)}"
    _autosize(sheet)

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def import_tally_excel_to_batch(db: Session, batch: Batch, user: User, data: bytes) -> TallyExcelImportResult:
    if batch.status != BatchStatus.DRAFT.value:
        raise InventoryError("Excel import is only available for draft batches")
    if batch.batch_type not in TALLY_EXCEL_IMPORT_BATCH_TYPES:
        raise InventoryError("Excel import is available for sale, issue, and purchase return batches")
    if batch.batch_type == BatchType.SALE.value:
        from app.services.sale_returns import ensure_sale_scan_allowed

        ensure_sale_scan_allowed(db, batch)

    lines = parse_bulk_assignment_xlsx(db, data, user=user, allow_product_create=False)
    total_quantity = sum(line.quantity for line in lines)
    if total_quantity < 1:
        raise InventoryError("Excel file has no importable quantity")
    if total_quantity > MAX_ASSIGNMENT_QUANTITY:
        raise InventoryError(f"Import {MAX_ASSIGNMENT_QUANTITY} items or fewer at a time")

    statuses = fefo_available_statuses(batch.batch_type)
    if not statuses:
        raise InventoryError("No FEFO-ready stock status is configured for this batch")

    picked = _pick_import_serials(db, lines, statuses)
    for line, serials in picked:
        rate = _line_rate(line)
        for serial in serials:
            db.add(BatchItem(batch_id=batch.id, serial_id=serial.id, rate=rate, fefo_picked=True))
            db.add(
                ScanLog(
                    serial_id=serial.id,
                    serial_number_raw=serial.serial_number,
                    user_id=user.id,
                    action=batch.batch_type,
                    batch_id=batch.id,
                    status="EXCEL_IMPORTED",
                    message="Imported from Tally Excel by FEFO",
                )
            )
    db.commit()
    return TallyExcelImportResult(product_lines=len(lines), quantity=total_quantity)


def _pick_import_serials(
    db: Session,
    lines: list[AssignmentLine],
    statuses: set[str],
) -> list[tuple[AssignmentLine, list[Serial]]]:
    selected_ids: set[int] = set()
    picked: list[tuple[AssignmentLine, list[Serial]]] = []
    for line in lines:
        candidates = [
            serial
            for serial in fefo_candidate_serials(
                db,
                line.product.id,
                line.quantity + len(selected_ids),
                statuses=statuses,
            )
            if serial.id not in selected_ids
        ][: line.quantity]
        if len(candidates) < line.quantity:
            available = len(candidates)
            raise InventoryError(
                f"Only {available} FEFO-ready serials are available for {line.product.product_code}"
            )
        selected_ids.update(serial.id for serial in candidates)
        picked.append((line, candidates))
    return picked


def _line_rate(line: AssignmentLine) -> float | None:
    if line.rate is None:
        return None
    if line.rate < Decimal("0"):
        raise InventoryError(f"Rate cannot be negative for {line.product.product_code}")
    return float(line.rate)


def _autosize(sheet) -> None:
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 12), 42)
