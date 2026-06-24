from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import barcode
from barcode.writer import ImageWriter
from PIL import Image as PILImage

from app.models import Batch, InventoryTransaction, ScanLog, Serial


def barcode_png(value: str) -> bytes:
    """Render a Code128 barcode (with the value as human-readable text) as PNG bytes."""
    writer = ImageWriter()
    code = barcode.get("code128", value, writer=writer)
    stream = BytesIO()
    code.write(stream, options={"module_height": 12.0, "font_size": 10, "text_distance": 3.0, "quiet_zone": 2.0})
    return stream.getvalue()


def scans_xlsx(scans: list[ScanLog]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Scans"
    sheet.append(["Date", "User", "Action", "Serial", "Status", "Batch", "Message", "Tally Reference"])
    for scan in scans:
        sheet.append(
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
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 12), 40)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def serials_xlsx(serials: list[Serial]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Barcodes"
    sheet.append(["Product Code", "Product Name", "Tally Stock Item", "Serial Number", "Status", "Created At"])
    for serial in serials:
        product = serial.product
        sheet.append(
            [
                product.product_code,
                product.product_name,
                product.tally_stock_item_name,
                serial.serial_number,
                serial.status,
                serial.created_at.isoformat(),
            ]
        )
    _autosize(sheet)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def transactions_xlsx(transactions: list[InventoryTransaction]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transactions"
    sheet.append(
        [
            "Date",
            "User",
            "Type",
            "Serial",
            "Product Code",
            "Product Name",
            "From Status",
            "To Status",
            "Reason",
            "Batch/Reference",
            "Tally Reference",
            "Notes",
        ]
    )
    for txn in transactions:
        sheet.append(
            [
                txn.created_at.isoformat(),
                txn.user.username,
                txn.transaction_type,
                txn.serial_number or "",
                txn.product.product_code if txn.product else "",
                txn.product.product_name if txn.product else "",
                txn.status_from or "",
                txn.status_to or "",
                txn.reason_code or "",
                txn.reference_number or "",
                txn.tally_reference or "",
                txn.notes or "",
            ]
        )
    _autosize(sheet)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _autosize(sheet) -> None:
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 12), 42)


def _label_image(value: str, target_width_mm: float = 52.0) -> Image:
    png = barcode_png(value)
    px_w, px_h = PILImage.open(BytesIO(png)).size
    width = target_width_mm * mm
    height = width * (px_h / px_w)
    return Image(BytesIO(png), width=width, height=height)


def barcode_labels_pdf(serials: list[Serial]) -> bytes:
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    cells = [_label_image(serial.serial_number) for serial in serials]
    rows = []
    for start in range(0, len(cells), 3):
        row = cells[start:start + 3]
        while len(row) < 3:
            row.append("")
        rows.append(row)

    styles = getSampleStyleSheet()
    story = [Paragraph("Barcode Labels", styles["Title"]), Spacer(1, 6 * mm)]
    if rows:
        table = Table(rows, colWidths=[58 * mm, 58 * mm, 58 * mm], rowHeights=34 * mm)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        story.append(table)
    doc.build(story)
    return stream.getvalue()


def audit_report_pdf(batch: Batch) -> bytes:
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Audit Report: {batch.batch_number}", styles["Title"]),
        Paragraph(f"Reference: {batch.party_name or '-'}", styles["BodyText"]),
        Paragraph(f"Status: {batch.status}", styles["BodyText"]),
        Spacer(1, 5 * mm),
    ]
    rows = [["Finding", "Serial", "Product", "Expected", "Scanned"]]
    for finding in batch.audit_findings:
        rows.append(
            [
                finding.finding_type,
                finding.serial_number,
                finding.product_name or "",
                finding.expected_status or "",
                finding.scanned_status or "",
            ]
        )
    table = Table(rows, repeatRows=1, colWidths=[28 * mm, 42 * mm, 58 * mm, 28 * mm, 28 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f2ff")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return stream.getvalue()
