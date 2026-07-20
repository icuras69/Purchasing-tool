import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy.orm import Session, selectinload

from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine


CSV_COLUMNS = [
    "purchase_order_id",
    "status",
    "created_at",
    "updated_at",
    "approved_at",
    "issued_at",
    "expected_delivery_date",
    "currency",
    "order_notes",
    "supplier_id",
    "supplier_code",
    "supplier_name",
    "supplier_email",
    "supplier_phone",
    "supplier_lead_time_days",
    "product_id",
    "orderpro_product_id",
    "sku",
    "barcode",
    "product_name",
    "product_description",
    "category",
    "pack_size",
    "current_stock",
    "quantity",
    "unit_cost",
    "line_total",
    "order_subtotal",
    "order_total",
    "line_notes",
    "supplier_sku",
    "supplier_product_name",
    "minimum_order_quantity",
    "lead_time_days",
]


FORMULA_PREFIXES = ("=", "+", "-", "@")
MONEY_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class PurchaseOrderCsvExport:
    content: bytes
    filename: str
    content_type: str = "text/csv; charset=utf-8"


@dataclass(frozen=True)
class PurchaseOrderHandoffPacket:
    content: bytes
    filename: str
    content_type: str = "application/zip"


HANDOFF_PACKET_SCHEMA_VERSION = "1.0"
HANDOFF_ELIGIBLE_STATUS = "issued"
HANDOFF_LINE_COLUMNS = [
    "local_line_id",
    "product_id",
    "orderpro_product_id",
    "sku",
    "product_name",
    "ordered_quantity",
    "unit_cost",
    "line_total",
    "currency",
    "pack_quantity",
    "number_of_packs",
    "minimum_order_quantity",
    "order_multiple",
    "pack_rule_adjustment_reason",
]
ZIP_ENTRY_NAMES = ("purchase_order.json", "purchase_order_lines.csv", "README.txt")


def load_purchase_order_for_export(db: Session, purchase_order_id: int) -> PurchaseOrder | None:
    return (
        db.query(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product),
        )
        .filter(PurchaseOrder.id == purchase_order_id)
        .first()
    )


def safe_csv_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def format_datetime(value: datetime | date | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def decimal_from_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def format_decimal(value: Any, *, money: bool = False) -> str:
    parsed = decimal_from_value(value)
    if parsed is None:
        return ""
    if money:
        parsed = parsed.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        return f"{parsed:.2f}"
    normalized = parsed.normalize()
    return format(normalized, "f")


def calculate_line_total(quantity: Any, unit_cost: Any) -> Decimal | None:
    parsed_quantity = decimal_from_value(quantity)
    parsed_unit_cost = decimal_from_value(unit_cost)
    if parsed_quantity is None or parsed_unit_cost is None:
        return None
    return (parsed_quantity * parsed_unit_cost).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def sanitize_filename_part(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "supplier")
    sanitized = sanitized.strip("._-")
    return sanitized or "supplier"


def sanitize_zip_filename_part(value: str | None) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value or "purchase-order")
    sanitized = sanitized.strip("-").lower()
    return sanitized or "purchase-order"


def purchase_order_csv_filename(po: PurchaseOrder) -> str:
    supplier_name = po.supplier.name if po.supplier else "supplier"
    created_date = po.created_at.date().isoformat() if po.created_at else datetime.utcnow().date().isoformat()
    return f"purchase_order_{po.id}_{sanitize_filename_part(supplier_name)}_{created_date}.csv"


def purchase_order_display_number(po: PurchaseOrder) -> str:
    return f"PO-{po.id}"


def purchase_order_handoff_filename(po: PurchaseOrder) -> str:
    return f"purchase-order-{sanitize_zip_filename_part(purchase_order_display_number(po))}-handoff.zip"


def purchase_order_rows(po: PurchaseOrder) -> list[dict[str, str]]:
    supplier = po.supplier
    rows: list[dict[str, str]] = []
    order_total = po.total_amount
    if order_total is None:
        line_totals = [calculate_line_total(line.quantity, line.unit_cost) for line in po.lines]
        totals = [line_total for line_total in line_totals if line_total is not None]
        order_total = sum(totals, Decimal("0")) if totals else None

    for line in po.lines:
        product = line.product
        line_total = line.line_total
        if line_total is None:
            line_total = calculate_line_total(line.quantity, line.unit_cost)

        row = {
            "purchase_order_id": format_decimal(po.id),
            "status": safe_csv_text(po.status),
            "created_at": format_datetime(po.created_at),
            "updated_at": format_datetime(po.updated_at),
            "approved_at": format_datetime(po.approved_at),
            "issued_at": format_datetime(po.issued_at),
            "expected_delivery_date": format_datetime(po.delivery_date),
            "currency": safe_csv_text(line.currency or po.currency),
            "order_notes": safe_csv_text(po.notes),
            "supplier_id": format_decimal(po.supplier_id),
            "supplier_code": safe_csv_text(supplier.orderpro_code if supplier else None),
            "supplier_name": safe_csv_text(supplier.name if supplier else None),
            "supplier_email": safe_csv_text(supplier.email if supplier else None),
            "supplier_phone": safe_csv_text(supplier.phone if supplier else None),
            "supplier_lead_time_days": format_decimal(supplier.lead_time_days if supplier else None),
            "product_id": format_decimal(line.product_id),
            "orderpro_product_id": safe_csv_text(product.orderpro_id if product else None),
            "sku": safe_csv_text((product.orderpro_sku if product else None) or line.supplier_sku),
            "barcode": safe_csv_text(product.barcode if product else None),
            "product_name": safe_csv_text((product.name if product else None) or line.supplier_product_name),
            "product_description": safe_csv_text(product.description if product else None),
            "category": safe_csv_text(product.category if product else None),
            "pack_size": format_decimal(line.pack_size),
            "current_stock": format_decimal(product.current_stock if product else None),
            "quantity": format_decimal(line.quantity),
            "unit_cost": format_decimal(line.unit_cost, money=True),
            "line_total": format_decimal(line_total, money=True),
            "order_subtotal": format_decimal(order_total, money=True),
            "order_total": format_decimal(order_total, money=True),
            "line_notes": safe_csv_text(line.notes),
            "supplier_sku": safe_csv_text(line.supplier_sku),
            "supplier_product_name": safe_csv_text(line.supplier_product_name),
            "minimum_order_quantity": format_decimal(line.minimum_order_quantity),
            "lead_time_days": format_decimal(line.lead_time_days),
        }
        rows.append(row)
    return rows


def build_purchase_order_csv(po: PurchaseOrder) -> PurchaseOrderCsvExport:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(purchase_order_rows(po))
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return PurchaseOrderCsvExport(content=content, filename=purchase_order_csv_filename(po))


def assert_purchase_order_handoff_eligible(po: PurchaseOrder) -> None:
    if po.status != HANDOFF_ELIGIBLE_STATUS:
        raise ValueError("Only locally issued purchase orders can generate a handoff packet.")
    if not po.lines:
        raise ValueError("Purchase order has no line items to include in the handoff packet.")


def isoformat_utc(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat()


def orderpro_linkage_fields(po: PurchaseOrder) -> dict[str, Any]:
    linkage: dict[str, Any] = {}
    for field_name in (
        "orderpro_id",
        "orderpro_po_id",
        "orderpro_purchase_order_id",
        "external_purchase_order_id",
    ):
        value = getattr(po, field_name, None)
        if value:
            linkage[field_name] = value
    return linkage


def purchase_order_handoff_json(po: PurchaseOrder, *, generated_at: datetime) -> dict[str, Any]:
    supplier = po.supplier
    payload: dict[str, Any] = {
        "packet_schema_version": HANDOFF_PACKET_SCHEMA_VERSION,
        "generated_at": isoformat_utc(generated_at),
        "local_purchase_order_id": po.id,
        "displayed_po_number": purchase_order_display_number(po),
        "status": po.status,
        "created_at": isoformat_utc(po.created_at),
        "updated_at": isoformat_utc(po.updated_at),
        "approved_at": isoformat_utc(po.approved_at),
        "issued_at": isoformat_utc(po.issued_at),
        "supplier": {
            "supplier_id": po.supplier_id,
            "canonical_supplier_name": supplier.name if supplier else None,
            "supplier_code": supplier.orderpro_code if supplier else None,
            "email": supplier.email if supplier else None,
            "phone": supplier.phone if supplier else None,
            "website": supplier.website if supplier else None,
            "contact_method": supplier.contact_method if supplier else None,
            "payment_terms": supplier.payment_terms if supplier else None,
        },
        "currency": po.currency,
        "subtotal": decimal_or_none(po.total_amount),
        "total": decimal_or_none(po.total_amount),
        "line_count": len(po.lines),
        "external_send_performed": False,
        "orderpro_po_created": False,
    }
    linkage = orderpro_linkage_fields(po)
    if linkage:
        payload["orderpro_linkage"] = linkage
    return payload


def decimal_or_none(value: Any) -> float | None:
    parsed = decimal_from_value(value)
    return float(parsed) if parsed is not None else None


def number_of_packs(quantity: Any, pack_size: Any) -> Decimal | None:
    parsed_quantity = decimal_from_value(quantity)
    parsed_pack_size = decimal_from_value(pack_size)
    if parsed_quantity is None or parsed_pack_size is None or parsed_pack_size <= 0:
        return None
    return parsed_quantity / parsed_pack_size


def pack_rule_adjustment_reason(line: PurchaseOrderLine) -> str:
    notes = line.notes or ""
    return notes if "Pack rule:" in notes else ""


def purchase_order_handoff_line_rows(po: PurchaseOrder) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in po.lines:
        product = line.product
        line_total = line.line_total
        if line_total is None:
            line_total = calculate_line_total(line.quantity, line.unit_cost)
        packs = number_of_packs(line.quantity, line.pack_size)
        rows.append(
            {
                "local_line_id": format_decimal(line.id),
                "product_id": format_decimal(line.product_id),
                "orderpro_product_id": safe_csv_text(product.orderpro_id if product else None),
                "sku": safe_csv_text((product.orderpro_sku if product else None) or line.supplier_sku),
                "product_name": safe_csv_text((product.name if product else None) or line.supplier_product_name),
                "ordered_quantity": format_decimal(line.quantity),
                "unit_cost": format_decimal(line.unit_cost, money=True),
                "line_total": format_decimal(line_total, money=True),
                "currency": safe_csv_text(line.currency or po.currency),
                "pack_quantity": format_decimal(line.pack_size),
                "number_of_packs": format_decimal(packs),
                "minimum_order_quantity": format_decimal(line.minimum_order_quantity),
                "order_multiple": format_decimal(line.pack_size),
                "pack_rule_adjustment_reason": safe_csv_text(pack_rule_adjustment_reason(line)),
            }
        )
    return rows


def build_handoff_lines_csv(po: PurchaseOrder) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HANDOFF_LINE_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(purchase_order_handoff_line_rows(po))
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def build_handoff_readme(po: PurchaseOrder, *, generated_at: datetime) -> str:
    supplier_name = po.supplier.name if po.supplier else "Unknown supplier"
    po_number = purchase_order_display_number(po)
    generated = isoformat_utc(generated_at)
    return "\n".join(
        [
            "Local Purchasing Tool Handoff Packet",
            "",
            f"Local PO: {po_number}",
            f"Supplier: {supplier_name}",
            f"Generated at: {generated}",
            "",
            "This is a local Purchasing Tool handoff packet.",
            "No OrderPro purchase order was created.",
            "Nothing was sent to the supplier.",
            "This packet requires manual review before external use.",
            "",
            "Files:",
            "- purchase_order.json: local PO header, supplier context, totals, and local-only flags.",
            "- purchase_order_lines.csv: one row per local PO line with product, quantity, cost, MOQ, and pack context.",
            "- README.txt: this safety and contents note.",
            "",
            "Deliberately deferred: OrderPro write-back, supplier email/send, and external PO creation.",
            "",
        ]
    )


def zip_info(name: str, *, generated_at: datetime) -> ZipInfo:
    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(timezone.utc).replace(tzinfo=None)
    info = ZipInfo(name)
    info.date_time = (
        generated_at.year,
        generated_at.month,
        generated_at.day,
        generated_at.hour,
        generated_at.minute,
        generated_at.second,
    )
    info.compress_type = ZIP_DEFLATED
    return info


def build_purchase_order_handoff_packet(
    po: PurchaseOrder,
    *,
    generated_at: datetime | None = None,
) -> PurchaseOrderHandoffPacket:
    assert_purchase_order_handoff_eligible(po)
    generated = generated_at or datetime.now(timezone.utc)
    json_payload = json.dumps(
        purchase_order_handoff_json(po, generated_at=generated),
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    lines_csv = build_handoff_lines_csv(po)
    readme = build_handoff_readme(po, generated_at=generated).encode("utf-8")

    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(zip_info(ZIP_ENTRY_NAMES[0], generated_at=generated), json_payload)
        archive.writestr(zip_info(ZIP_ENTRY_NAMES[1], generated_at=generated), lines_csv)
        archive.writestr(zip_info(ZIP_ENTRY_NAMES[2], generated_at=generated), readme)

    return PurchaseOrderHandoffPacket(
        content=output.getvalue(),
        filename=purchase_order_handoff_filename(po),
    )
