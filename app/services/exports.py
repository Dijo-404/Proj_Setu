from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import qrcode

from app.models import Batch, ScanLog, Serial


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


def qr_labels_pdf(serials: list[Serial]) -> bytes:
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    data = []
    row = []
    for serial in serials:
        image = qrcode.make(serial.serial_number)
        image_stream = BytesIO()
        image.save(image_stream, format="PNG")
        image_stream.seek(0)
        cell = [Image(image_stream, width=36 * mm, height=36 * mm), serial.serial_number]
        row.append(cell)
        if len(row) == 3:
            data.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        data.append(row)

    styles = getSampleStyleSheet()
    story = [Paragraph("QR Labels", styles["Title"]), Spacer(1, 6 * mm)]
    table_data = []
    for row in data:
        rendered = []
        for cell in row:
            if not cell:
                rendered.append("")
                continue
            rendered.append(make_label_cell(cell[0], cell[1]))
        table_data.append(rendered)
    if table_data:
        table = Table(table_data, colWidths=[58 * mm, 58 * mm, 58 * mm], rowHeights=58 * mm)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(table)
    doc.build(story)
    return stream.getvalue()


def make_label_cell(image: Image, serial_number: str):
    styles = getSampleStyleSheet()
    return Table(
        [
            [image],
            [Paragraph(serial_number, styles["BodyText"])],
        ],
        rowHeights=[40 * mm, 10 * mm],
    )


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
