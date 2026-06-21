from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.models import Batch
from app.services.inventory import group_batch_items


TWOPLACES = Decimal("0.01")


def money(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VoucherLine:
    product_id: int
    product_code: str
    product_name: str
    tally_stock_item_name: str
    hsn: str
    gst_rate: Decimal
    unit: str
    quantity: int
    rate: Decimal
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class VoucherSummary:
    lines: list[VoucherLine]
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    gst_amount: Decimal
    rounded_total_before_round_off: Decimal
    round_off: Decimal
    final_value: Decimal


def calculate_voucher_summary(batch: Batch) -> VoucherSummary:
    lines = []
    taxable_total = Decimal("0")
    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")

    for group in group_batch_items(batch):
        product = group["product"]
        quantity = int(group["quantity"])
        rate = money(group.get("rate") or product.default_rate)
        taxable_value = money(rate * quantity)
        gst_rate = money(product.gst_rate)
        gst_amount = money(taxable_value * gst_rate / Decimal("100"))
        cgst_amount = money(gst_amount / Decimal("2"))
        sgst_amount = money(gst_amount - cgst_amount)
        igst_amount = Decimal("0.00")
        line_total = money(taxable_value + cgst_amount + sgst_amount + igst_amount)
        taxable_total += taxable_value
        cgst_total += cgst_amount
        sgst_total += sgst_amount
        igst_total += igst_amount
        lines.append(
            VoucherLine(
                product_id=product.id,
                product_code=product.product_code,
                product_name=product.product_name,
                tally_stock_item_name=product.tally_stock_item_name,
                hsn=product.hsn,
                gst_rate=gst_rate,
                unit=product.unit,
                quantity=quantity,
                rate=rate,
                taxable_value=taxable_value,
                cgst_amount=cgst_amount,
                sgst_amount=sgst_amount,
                igst_amount=igst_amount,
                line_total=line_total,
            )
        )

    gst_total = money(cgst_total + sgst_total + igst_total)
    before_round_off = money(taxable_total + gst_total)
    final_value = before_round_off.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    round_off = money(final_value - before_round_off)
    return VoucherSummary(
        lines=lines,
        taxable_value=money(taxable_total),
        cgst_amount=money(cgst_total),
        sgst_amount=money(sgst_total),
        igst_amount=money(igst_total),
        gst_amount=gst_total,
        rounded_total_before_round_off=before_round_off,
        round_off=round_off,
        final_value=money(final_value),
    )


def validate_priced_batch(batch: Batch) -> None:
    summary = calculate_voucher_summary(batch)
    if batch.batch_type == "AUDIT":
        return
    missing = [line.product_name for line in summary.lines if line.rate <= 0]
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ValueError(f"Set a positive rate for: {names}")
