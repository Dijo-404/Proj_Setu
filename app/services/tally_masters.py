from __future__ import annotations

from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Product, TallyMasterConfirmation, User, utc_now
from app.services.settings import get_all_settings, parse_sales_gst_ledger_mappings


@dataclass(frozen=True)
class MasterRequirement:
    master_type: str
    master_name: str
    source: str
    detail: str
    local_status: str

    @property
    def key(self) -> str:
        return f"{self.master_type}|{self.master_name}"


@dataclass(frozen=True)
class GatewayCheckResult:
    ok: bool
    message: str
    response_excerpt: str = ""


def _status(name: str | None) -> str:
    return "READY" if name and name.strip() else "MISSING"


def _add(requirements: dict[tuple[str, str], MasterRequirement], master_type: str, name: str, source: str, detail: str) -> None:
    clean = (name or "").strip()
    key = (master_type, clean)
    if key in requirements:
        existing = requirements[key]
        requirements[key] = MasterRequirement(
            master_type=existing.master_type,
            master_name=existing.master_name,
            source=f"{existing.source}; {source}",
            detail=existing.detail,
            local_status=existing.local_status,
        )
        return
    requirements[key] = MasterRequirement(master_type, clean, source, detail, _status(clean))


def collect_master_requirements(db: Session) -> list[MasterRequirement]:
    settings = get_all_settings(db)
    requirements: dict[tuple[str, str], MasterRequirement] = {}

    _add(requirements, "Company", settings["company_name"], "Settings", "Must be the open Tally company")
    _add(requirements, "Voucher Type", settings["sales_voucher_type"], "Settings", "Used for sale batches")
    _add(requirements, "Voucher Type", settings["purchase_voucher_type"], "Settings", "Used for receive batches")
    _add(requirements, "Ledger", settings["sales_ledger_name"], "Settings", "Sales posting ledger")
    _add(requirements, "Ledger", settings["purchase_ledger_name"], "Settings", "Purchase posting ledger")
    _add(requirements, "Ledger", settings["cgst_ledger_name"], "Settings", "GST posting ledger")
    _add(requirements, "Ledger", settings["sgst_ledger_name"], "Settings", "GST posting ledger")
    _add(requirements, "Ledger", settings["round_off_ledger_name"], "Settings", "Round off posting ledger")
    mappings = parse_sales_gst_ledger_mappings(settings.get("sales_gst_ledger_mappings"))
    for gst_rate, ledgers in mappings.items():
        source = f"Sales GST {gst_rate}% mapping"
        _add(requirements, "Ledger", ledgers["sales"], source, "Sales posting ledger")
        _add(requirements, "Ledger", ledgers["cgst"], source, "CGST posting ledger")
        _add(requirements, "Ledger", ledgers["sgst"], source, "SGST posting ledger")
        if ledgers["igst"]:
            _add(requirements, "Ledger", ledgers["igst"], source, "IGST posting ledger")

    products = db.scalars(select(Product).where(Product.active == True).order_by(Product.product_code)).all()
    for product in products:
        source = f"Product {product.product_code}"
        _add(requirements, "Stock Item", product.tally_stock_item_name, source, product.product_name)
        _add(requirements, "Unit", product.unit, source, "Product unit of measure")
        _add(requirements, "HSN", product.hsn, source, f"GST rate {product.gst_rate}%")

    return sorted(requirements.values(), key=lambda item: (item.master_type, item.master_name))


def confirmation_lookup(db: Session) -> dict[str, TallyMasterConfirmation]:
    rows = db.scalars(select(TallyMasterConfirmation).options(selectinload(TallyMasterConfirmation.confirmed_by))).all()
    return {f"{row.master_type}|{row.master_name}": row for row in rows}


def confirm_master(db: Session, user: User, master_type: str, master_name: str, source: str, notes: str = "") -> None:
    clean_type = master_type.strip()
    clean_name = master_name.strip()
    row = db.scalar(
        select(TallyMasterConfirmation).where(
            TallyMasterConfirmation.master_type == clean_type,
            TallyMasterConfirmation.master_name == clean_name,
        )
    )
    if row:
        row.source = source.strip()
        row.notes = notes.strip() or None
        row.confirmed_by_id = user.id
        row.confirmed_at = utc_now()
    else:
        db.add(
            TallyMasterConfirmation(
                master_type=clean_type,
                master_name=clean_name,
                source=source.strip(),
                notes=notes.strip() or None,
                confirmed_by_id=user.id,
            )
        )
    db.commit()


def remove_confirmation(db: Session, master_type: str, master_name: str) -> None:
    row = db.scalar(
        select(TallyMasterConfirmation).where(
            TallyMasterConfirmation.master_type == master_type.strip(),
            TallyMasterConfirmation.master_name == master_name.strip(),
        )
    )
    if row:
        db.delete(row)
        db.commit()


def readiness_counts(requirements: list[MasterRequirement], confirmations: dict[str, TallyMasterConfirmation]) -> dict[str, int]:
    missing = sum(1 for item in requirements if item.local_status == "MISSING")
    confirmed = sum(1 for item in requirements if item.local_status == "READY" and item.key in confirmations)
    ready = sum(1 for item in requirements if item.local_status == "READY")
    return {
        "total": len(requirements),
        "ready": ready,
        "missing": missing,
        "confirmed": confirmed,
        "unchecked": max(ready - confirmed, 0),
    }


def live_sync_readiness(db: Session) -> tuple[bool, dict[str, int]]:
    requirements = collect_master_requirements(db)
    confirmations = confirmation_lookup(db)
    counts = readiness_counts(requirements, confirmations)
    return counts["missing"] == 0 and counts["unchecked"] == 0 and counts["total"] > 0, counts


def build_company_list_xml() -> str:
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "Export"
    ET.SubElement(header, "TYPE").text = "Collection"
    ET.SubElement(header, "ID").text = "List of Companies"
    body = ET.SubElement(envelope, "BODY")
    desc = ET.SubElement(body, "DESC")
    static_variables = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(static_variables, "SVEXPORTFORMAT").text = "$$SysName:XML"
    tdl = ET.SubElement(desc, "TDL")
    tdl_message = ET.SubElement(tdl, "TDLMESSAGE")
    collection = ET.SubElement(tdl_message, "COLLECTION", {"NAME": "List of Companies"})
    ET.SubElement(collection, "TYPE").text = "Company"
    ET.SubElement(collection, "NATIVEMETHOD").text = "Name"
    return ET.tostring(envelope, encoding="unicode")


def test_tally_gateway(settings: dict[str, str]) -> GatewayCheckResult:
    xml = build_company_list_xml()
    url = f"http://{settings['tally_host']}:{settings['tally_port']}"
    request = Request(url, data=xml.encode("utf-8"), headers={"Content-Type": "text/xml"}, method="POST")
    try:
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        return GatewayCheckResult(False, f"Tally gateway did not respond: {exc.reason}")
    except TimeoutError:
        return GatewayCheckResult(False, "Tally gateway timed out")
    excerpt = " ".join(body.split())[:500]
    if not body.strip():
        return GatewayCheckResult(False, "Tally gateway returned an empty response")
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return GatewayCheckResult(False, "Tally gateway returned unreadable XML", excerpt)

    errors = [
        node.text.strip()
        for node in root.iter()
        if node.tag.upper().endswith("LINEERROR") and node.text and node.text.strip()
    ]
    if errors:
        return GatewayCheckResult(False, f"Tally rejected gateway check: {'; '.join(errors)}", excerpt)

    status = next(
        (node.text.strip() for node in root.iter() if node.tag.upper().endswith("STATUS") and node.text),
        None,
    )
    if status == "0":
        return GatewayCheckResult(False, "Tally rejected gateway check", excerpt)
    return GatewayCheckResult(True, "Tally gateway responded", excerpt)
