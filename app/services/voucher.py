from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.models import Batch, GstTreatment
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
    discount_rate: Decimal
    gross_value: Decimal
    discount_amount: Decimal
    taxable_value: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
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
    is_interstate_sale = (
        batch.batch_type == "SALE"
        and (getattr(batch, "gst_treatment", None) or "").upper() == GstTreatment.INTER_STATE.value
    )

    for group in group_batch_items(batch):
        product = group["product"]
        quantity = int(group["quantity"])
        rate = money(group.get("rate") or product.default_rate)
        gross_value = money(rate * quantity)
        discount_rate = money(product.sales_discount_rate if batch.batch_type == "SALE" else 0)
        discount_amount = money(gross_value * discount_rate / Decimal("100"))
        taxable_value = money(gross_value - discount_amount)
        product_gst_rate = money(product.gst_rate)
        gst_rate = product_gst_rate
        batch_cgst_rate = getattr(batch, "gst_cgst_rate", None)
        batch_sgst_rate = getattr(batch, "gst_sgst_rate", None)
        batch_igst_rate = getattr(batch, "gst_igst_rate", None)
        if is_interstate_sale:
            igst_rate = money(batch_igst_rate if batch_igst_rate is not None else product_gst_rate)
            gst_rate = igst_rate
            cgst_amount = Decimal("0.00")
            sgst_amount = Decimal("0.00")
            igst_amount = money(taxable_value * igst_rate / Decimal("100"))
            cgst_rate = Decimal("0.00")
            sgst_rate = Decimal("0.00")
        elif batch.batch_type == "SALE" and batch_cgst_rate is not None and batch_sgst_rate is not None:
            cgst_rate = money(batch_cgst_rate)
            sgst_rate = money(batch_sgst_rate)
            igst_rate = Decimal("0.00")
            gst_rate = money(cgst_rate + sgst_rate)
            cgst_amount = money(taxable_value * cgst_rate / Decimal("100"))
            sgst_amount = money(taxable_value * sgst_rate / Decimal("100"))
            igst_amount = Decimal("0.00")
        else:
            gst_amount = money(taxable_value * gst_rate / Decimal("100"))
            cgst_rate = money(gst_rate / Decimal("2"))
            sgst_rate = money(gst_rate - cgst_rate)
            igst_rate = Decimal("0.00")
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
                discount_rate=discount_rate,
                gross_value=gross_value,
                discount_amount=discount_amount,
                taxable_value=taxable_value,
                cgst_rate=cgst_rate,
                sgst_rate=sgst_rate,
                igst_rate=igst_rate,
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
