import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

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


def purchase_order_csv_filename(po: PurchaseOrder) -> str:
    supplier_name = po.supplier.name if po.supplier else "supplier"
    created_date = po.created_at.date().isoformat() if po.created_at else datetime.utcnow().date().isoformat()
    return f"purchase_order_{po.id}_{sanitize_filename_part(supplier_name)}_{created_date}.csv"


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
