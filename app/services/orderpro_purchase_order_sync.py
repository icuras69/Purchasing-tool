from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.orderpro_client import OrderProClient, extract_records
from app.services.orderpro_sync_planner import (
    changed_fields,
    clean_text,
    fetch_orderpro_records_with_status,
    parse_datetime,
    parse_order_quantity,
    sanitize_snapshot,
    sync_time_without_timezone,
    to_optional_float,
)


OPEN_ORDERPRO_PURCHASE_ORDER_STATUSES = {
    "partial",
    "partially_received",
    "sent",
}
EXCLUDED_ORDERPRO_PURCHASE_ORDER_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "received",
    "fully_received",
    "draft",
    "rejected",
    "void",
}


def is_open_orderpro_purchase_order_status(status: str | None) -> bool:
    return normalize_orderpro_purchase_order_status(status) in OPEN_ORDERPRO_PURCHASE_ORDER_STATUSES


def normalize_orderpro_purchase_order_status(status: str | None) -> str:
    return (status or "").strip().lower().replace(" ", "_").replace("-", "_")


def extract_purchase_order_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "lines", "purchase_order_items", "po_items"):
        value = row.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in extract_records(value) if isinstance(item, dict)]
    return []


def purchase_order_supplier_payload(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("supplier") if isinstance(row.get("supplier"), dict) else {}


def purchase_order_supplier_id(row: dict[str, Any]) -> str | None:
    supplier = purchase_order_supplier_payload(row)
    return clean_text(row.get("supplier_id")) or clean_text(supplier.get("id"))


def purchase_order_supplier_code(row: dict[str, Any]) -> str | None:
    supplier = purchase_order_supplier_payload(row)
    return clean_text(row.get("supplier_code")) or clean_text(supplier.get("code"))


def purchase_order_supplier_name(row: dict[str, Any]) -> str | None:
    supplier = purchase_order_supplier_payload(row)
    return clean_text(row.get("supplier_name")) or clean_text(supplier.get("name"))


def purchase_order_line_product_payload(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("product") if isinstance(item.get("product"), dict) else {}


def purchase_order_line_product_id(item: dict[str, Any]) -> str | None:
    product = purchase_order_line_product_payload(item)
    return clean_text(item.get("product_id")) or clean_text(product.get("id"))


def purchase_order_line_sku(item: dict[str, Any]) -> str | None:
    product = purchase_order_line_product_payload(item)
    return clean_text(item.get("sku")) or clean_text(item.get("product_sku")) or clean_text(product.get("sku"))


def purchase_order_line_barcode(item: dict[str, Any]) -> str | None:
    product = purchase_order_line_product_payload(item)
    return clean_text(item.get("barcode")) or clean_text(product.get("barcode"))


def purchase_order_line_name(item: dict[str, Any]) -> str | None:
    product = purchase_order_line_product_payload(item)
    return clean_text(item.get("product_name")) or clean_text(item.get("name")) or clean_text(product.get("name"))


def purchase_order_line_key(order_row: dict[str, Any], item: dict[str, Any], index: int) -> str:
    order_id = clean_text(order_row.get("id")) or "unknown-po"
    line_id = clean_text(item.get("id")) or clean_text(item.get("line_id"))
    if line_id:
        return line_id
    identity = purchase_order_line_product_id(item) or purchase_order_line_sku(item) or purchase_order_line_name(item) or "unknown"
    return f"{order_id}:{index}:{identity}"


def parse_purchase_order_line_quantities(item: dict[str, Any]) -> tuple[float | None, float | None, float | None, float, list[str]]:
    warnings = []
    direct_open = first_quantity(item, ("quantity_open", "qty_open", "open_qty", "remaining_qty", "qty_remaining", "qty"))
    received = first_quantity(item, ("quantity_received", "qty_received", "received_qty", "qty_received_total"))
    cancelled = first_quantity(item, ("quantity_cancelled", "qty_cancelled", "cancelled_qty", "canceled_qty"))
    if direct_open is not None:
        quantity_open = max(direct_open, 0.0)
        explicit_ordered = first_quantity(item, ("quantity_ordered", "qty_ordered", "ordered_qty", "quantity"))
        ordered = explicit_ordered if explicit_ordered is not None else quantity_open + (received or 0.0)
        cancelled = cancelled if cancelled is not None else 0.0
    else:
        ordered = first_quantity(item, ("quantity_ordered", "qty_ordered", "ordered_qty", "quantity"))
        if ordered is None:
            warnings.append("missing_open_and_ordered_quantity")
            quantity_open = 0.0
        else:
            if received is None:
                warnings.append("missing_received_quantity_fallback")
            quantity_open = max(ordered - (received or 0.0) - (cancelled or 0.0), 0.0)
            cancelled = cancelled if cancelled is not None else 0.0
    return ordered, received, cancelled, round(quantity_open, 4), warnings


def first_quantity(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        parsed = parse_order_quantity(item.get(key))
        if parsed["present"] and not parsed["invalid"]:
            return parsed["value"]
    return None


def quantity_field_present(item: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(parse_order_quantity(item.get(key))["present"] for key in keys)


def quantity_field_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        parsed = parse_order_quantity(item.get(key))
        if parsed["present"]:
            return item.get(key)
    return None


def quantity_report(purchase_orders: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = Counter()
    open_by_status: Counter[str] = Counter()
    included_open_by_status: Counter[str] = Counter()
    excluded_quantity_by_status: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    line_samples_by_status: dict[str, dict[str, Any]] = {}
    sample_open_lines: list[dict[str, Any]] = []
    sample_received_lines: list[dict[str, Any]] = []
    cancelled_field_seen = False

    for order in purchase_orders:
        status = normalize_orderpro_purchase_order_status(clean_text(order.get("status")) or "unknown")
        included = is_open_orderpro_purchase_order_status(status)
        for item in extract_purchase_order_items(order):
            if quantity_field_present(item, ("qty", "quantity_open", "qty_open", "open_qty", "remaining_qty", "qty_remaining")):
                coverage["qty_present_count"] += 1
            if quantity_field_present(item, ("quantity_received", "qty_received", "received_qty", "qty_received_total")):
                coverage["qty_received_present_count"] += 1
            if quantity_field_present(item, ("unit_cost", "unit_price", "cost_price", "price")):
                coverage["unit_cost_present_count"] += 1
            if quantity_field_present(item, ("quantity_cancelled", "qty_cancelled", "cancelled_qty", "canceled_qty")):
                cancelled_field_seen = True
                coverage["qty_cancelled_present_count"] += 1

            ordered, received, cancelled, open_qty, warnings = parse_purchase_order_line_quantities(item)
            for warning in warnings:
                warning_counts[warning] += 1

            open_by_status[status] += open_qty
            if included:
                included_open_by_status[status] += open_qty
            else:
                excluded_quantity_by_status[status] += open_qty

            line_summary = {
                "orderpro_purchase_order_id": clean_text(order.get("id")),
                "status": status,
                "line_id": clean_text(item.get("id")) or clean_text(item.get("line_id")),
                "product_id": purchase_order_line_product_id(item),
                "sku": purchase_order_line_sku(item),
                "line_keys": sorted(str(key) for key in item.keys()),
                "qty": quantity_field_value(item, ("qty", "quantity_open", "qty_open", "open_qty", "remaining_qty", "qty_remaining")),
                "qty_received": quantity_field_value(item, ("qty_received", "quantity_received", "received_qty", "qty_received_total")),
                "unit_cost": quantity_field_value(item, ("unit_cost", "unit_price", "cost_price", "price")),
                "quantity_ordered": ordered,
                "quantity_received": received,
                "quantity_cancelled": cancelled,
                "quantity_open": open_qty,
            }
            line_samples_by_status.setdefault(status, line_summary)
            if included and open_qty > 0 and len(sample_open_lines) < 10:
                sample_open_lines.append(line_summary)
            if status == "received" and open_qty == 0 and (received or 0) > 0 and len(sample_received_lines) < 10:
                sample_received_lines.append(line_summary)

    notes = []
    if not cancelled_field_seen and any(extract_purchase_order_items(order) for order in purchase_orders):
        notes.append("OrderPro does not expose cancelled quantity in sampled lines; using 0.")

    return {
        "quantity_field_coverage": dict(coverage),
        "open_quantity_by_status": {status: round(quantity, 2) for status, quantity in open_by_status.items()},
        "included_open_quantity_total": round(sum(included_open_by_status.values()), 2),
        "excluded_quantity_by_status": {status: round(quantity, 2) for status, quantity in excluded_quantity_by_status.items()},
        "warning_counts_by_type": dict(warning_counts),
        "report_notes": notes,
        "line_samples_by_status": line_samples_by_status,
        "sample_open_lines": sample_open_lines,
        "sample_received_lines": sample_received_lines,
    }


def resolve_purchase_order_product(
    item: dict[str, Any],
    *,
    product_by_orderpro_id: dict[str, Product],
    product_by_sku: dict[str, Product],
    product_by_unique_barcode: dict[str, Product],
    ambiguous_barcodes: set[str],
) -> tuple[Product | None, str | None]:
    orderpro_product_id = purchase_order_line_product_id(item)
    sku = purchase_order_line_sku(item)
    barcode = purchase_order_line_barcode(item)
    if orderpro_product_id and orderpro_product_id in product_by_orderpro_id:
        return product_by_orderpro_id[orderpro_product_id], "orderpro_product_id"
    if sku and sku in product_by_sku:
        return product_by_sku[sku], "sku"
    if barcode and barcode in ambiguous_barcodes:
        return None, "ambiguous_barcode"
    if barcode and barcode in product_by_unique_barcode:
        return product_by_unique_barcode[barcode], "barcode"
    return None, None


def resolve_purchase_order_supplier(
    row: dict[str, Any],
    *,
    supplier_by_orderpro_id: dict[str, Supplier],
    supplier_by_code: dict[str, Supplier],
    supplier_by_unique_name: dict[str, Supplier],
) -> tuple[Supplier | None, str | None]:
    orderpro_supplier_id = purchase_order_supplier_id(row)
    supplier_code = purchase_order_supplier_code(row)
    supplier_name = purchase_order_supplier_name(row)
    normalized_name = supplier_name.lower().strip() if supplier_name else None
    if orderpro_supplier_id and orderpro_supplier_id in supplier_by_orderpro_id:
        return supplier_by_orderpro_id[orderpro_supplier_id], "orderpro_supplier_id"
    if supplier_code and supplier_code in supplier_by_code:
        return supplier_by_code[supplier_code], "supplier_code"
    if normalized_name and normalized_name in supplier_by_unique_name:
        return supplier_by_unique_name[normalized_name], "supplier_name"
    return None, None


def desired_purchase_order_fields(row: dict[str, Any], supplier: Supplier | None, synced_at: datetime) -> dict[str, Any]:
    return {
        "orderpro_id": clean_text(row.get("id")),
        "purchase_order_number": clean_text(row.get("po_number")) or clean_text(row.get("purchase_order_number")) or clean_text(row.get("number")),
        "supplier_id": supplier.id if supplier else None,
        "orderpro_supplier_id": purchase_order_supplier_id(row),
        "supplier_code": purchase_order_supplier_code(row),
        "supplier_name": purchase_order_supplier_name(row),
        "status": clean_text(row.get("status")),
        "order_date": parse_datetime(row.get("order_date") or row.get("date") or row.get("created_at")),
        "expected_date": parse_datetime(row.get("expected_date") or row.get("due_date") or row.get("delivery_date") or row.get("eta")),
        "received_date": parse_datetime(row.get("received_date") or row.get("received_at")),
        "raw_payload": sanitize_snapshot(row),
        "last_synced_at": synced_at,
        "updated_at": synced_at,
    }


def desired_purchase_order_line_fields(
    order_row: dict[str, Any],
    item: dict[str, Any],
    *,
    index: int,
    product: Product | None,
    synced_at: datetime,
) -> tuple[dict[str, Any], list[str]]:
    ordered, received, cancelled, open_qty, warnings = parse_purchase_order_line_quantities(item)
    return {
        "orderpro_line_id": clean_text(item.get("id")) or clean_text(item.get("line_id")),
        "orderpro_line_key": purchase_order_line_key(order_row, item, index),
        "product_id": product.id if product else None,
        "orderpro_product_id": purchase_order_line_product_id(item),
        "sku": purchase_order_line_sku(item),
        "barcode": purchase_order_line_barcode(item),
        "product_name": purchase_order_line_name(item),
        "quantity_ordered": ordered,
        "quantity_received": received,
        "quantity_cancelled": cancelled,
        "quantity_open": open_qty,
        "unit_cost": to_optional_float(item.get("unit_cost") or item.get("unit_price") or item.get("cost_price") or item.get("price")),
        "expected_date": parse_datetime(item.get("expected_date") or item.get("due_date") or item.get("eta") or order_row.get("expected_date") or order_row.get("due_date")),
        "raw_payload": sanitize_snapshot(item),
        "updated_at": synced_at,
    }, warnings


def build_product_indexes(db: Session):
    products = db.query(Product).all()
    by_orderpro_id = {str(product.orderpro_id): product for product in products if product.orderpro_id}
    by_sku = {product.orderpro_sku: product for product in products if product.orderpro_sku}
    barcode_counts = Counter(product.barcode for product in products if product.barcode)
    unique_barcodes = {
        product.barcode: product for product in products if product.barcode and barcode_counts[product.barcode] == 1
    }
    ambiguous_barcodes = {barcode for barcode, count in barcode_counts.items() if count > 1}
    return by_orderpro_id, by_sku, unique_barcodes, ambiguous_barcodes


def build_supplier_indexes(db: Session):
    suppliers = db.query(Supplier).all()
    by_orderpro_id = {str(supplier.orderpro_id): supplier for supplier in suppliers if supplier.orderpro_id}
    by_code = {supplier.orderpro_code: supplier for supplier in suppliers if supplier.orderpro_code}
    name_counts = Counter((supplier.normalized_name or supplier.name or "").lower().strip() for supplier in suppliers)
    by_unique_name = {
        (supplier.normalized_name or supplier.name or "").lower().strip(): supplier
        for supplier in suppliers
        if name_counts[(supplier.normalized_name or supplier.name or "").lower().strip()] == 1
    }
    return by_orderpro_id, by_code, by_unique_name


def plan_orderpro_purchase_order_sync(db: Session, purchase_orders: list[dict[str, Any]]) -> dict[str, Any]:
    product_by_id, product_by_sku, product_by_barcode, ambiguous_barcodes = build_product_indexes(db)
    supplier_by_id, supplier_by_code, supplier_by_name = build_supplier_indexes(db)
    existing_pos = {po.orderpro_id: po for po in db.query(OrderProPurchaseOrder).all()}
    synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    purchase_orders_to_create = []
    purchase_orders_to_update = []
    purchase_orders_matching = []
    lines_to_create = []
    lines_to_update = []
    lines_matching = []
    statuses = Counter()
    product_link_methods = Counter()
    supplier_link_methods = Counter()
    items_missing_product = []
    headers_missing_supplier = []
    lines_total = 0
    open_qty_total = 0.0
    quantities = quantity_report(purchase_orders)

    for row in purchase_orders:
        statuses[clean_text(row.get("status")) or "unknown"] += 1
        orderpro_id = clean_text(row.get("id"))
        if not orderpro_id:
            continue
        supplier, supplier_method = resolve_purchase_order_supplier(
            row,
            supplier_by_orderpro_id=supplier_by_id,
            supplier_by_code=supplier_by_code,
            supplier_by_unique_name=supplier_by_name,
        )
        if supplier_method:
            supplier_link_methods[supplier_method] += 1
        else:
            headers_missing_supplier.append({"orderpro_id": clean_text(row.get("id")), "supplier_name": purchase_order_supplier_name(row)})
        existing_po = existing_pos.get(orderpro_id)
        desired_header = desired_purchase_order_fields(row, supplier, synced_at)
        if existing_po is None:
            purchase_orders_to_create.append({"orderpro_id": orderpro_id, "purchase_order_number": desired_header["purchase_order_number"]})
            existing_lines = {}
        else:
            header_changes = changed_fields(existing_po, desired_header)
            if header_changes:
                purchase_orders_to_update.append({"local_id": existing_po.id, "orderpro_id": orderpro_id, "changed_fields": sorted(header_changes)})
            else:
                purchase_orders_matching.append({"local_id": existing_po.id, "orderpro_id": orderpro_id})
            existing_lines = {line.orderpro_line_key: line for line in existing_po.lines}
        for index, item in enumerate(extract_purchase_order_items(row), start=1):
            lines_total += 1
            product, product_method = resolve_purchase_order_product(
                item,
                product_by_orderpro_id=product_by_id,
                product_by_sku=product_by_sku,
                product_by_unique_barcode=product_by_barcode,
                ambiguous_barcodes=ambiguous_barcodes,
            )
            if product_method:
                product_link_methods[product_method] += 1
            else:
                items_missing_product.append({"orderpro_id": clean_text(row.get("id")), "sku": purchase_order_line_sku(item), "barcode": purchase_order_line_barcode(item)})
            desired, _warnings = desired_purchase_order_line_fields(
                row,
                item,
                index=index,
                product=product,
                synced_at=synced_at,
            )
            open_qty_total += desired["quantity_open"]
            existing_line = existing_lines.get(desired["orderpro_line_key"])
            if existing_line is None:
                lines_to_create.append(
                    {
                        "orderpro_id": orderpro_id,
                        "line_key": desired["orderpro_line_key"],
                        "sku": desired["sku"],
                        "quantity_open": desired["quantity_open"],
                    }
                )
            else:
                line_changes = changed_fields(existing_line, desired)
                if line_changes:
                    lines_to_update.append(
                        {"local_id": existing_line.id, "line_key": desired["orderpro_line_key"], "changed_fields": sorted(line_changes)}
                    )
                else:
                    lines_matching.append({"local_id": existing_line.id, "line_key": desired["orderpro_line_key"]})

    return {
        "mode": "dry_run",
        "summary": {
            "purchase_orders_fetched": len(purchase_orders),
            "purchase_order_lines_fetched": lines_total,
            "purchase_orders_to_create": len(purchase_orders_to_create),
            "purchase_orders_to_update": len(purchase_orders_to_update),
            "purchase_orders_already_matching": len(purchase_orders_matching),
            "purchase_order_lines_to_create": len(lines_to_create),
            "purchase_order_lines_to_update": len(lines_to_update),
            "purchase_order_lines_already_matching": len(lines_matching),
            "status_counts": dict(statuses),
            "product_link_methods": dict(product_link_methods),
            "supplier_link_methods": dict(supplier_link_methods),
            "items_missing_product_match": len(items_missing_product),
            "headers_missing_supplier_match": len(headers_missing_supplier),
            "open_quantity_total": round(open_qty_total, 2),
            "included_open_quantity_total": quantities["included_open_quantity_total"],
            "quantity_warning_count": sum(quantities["warning_counts_by_type"].values()),
            "quantity_field_coverage": quantities["quantity_field_coverage"],
            "open_quantity_by_status": quantities["open_quantity_by_status"],
            "excluded_quantity_by_status": quantities["excluded_quantity_by_status"],
            "warning_counts_by_type": quantities["warning_counts_by_type"],
        },
        "report_notes": quantities["report_notes"],
        "line_samples_by_status": quantities["line_samples_by_status"],
        "sample_open_lines": quantities["sample_open_lines"],
        "sample_received_lines": quantities["sample_received_lines"],
        "purchase_orders_to_create_sample": purchase_orders_to_create[:10],
        "purchase_orders_to_update_sample": purchase_orders_to_update[:10],
        "purchase_order_lines_to_create_sample": lines_to_create[:10],
        "purchase_order_lines_to_update_sample": lines_to_update[:10],
        "items_missing_product_match_sample": items_missing_product[:10],
        "headers_missing_supplier_match_sample": headers_missing_supplier[:10],
        "warnings": [],
    }


def apply_orderpro_purchase_order_sync(db: Session, purchase_orders: list[dict[str, Any]], *, synced_at: datetime | None = None) -> dict[str, Any]:
    sync_time = sync_time_without_timezone(synced_at or datetime.now(timezone.utc))
    product_by_id, product_by_sku, product_by_barcode, ambiguous_barcodes = build_product_indexes(db)
    supplier_by_id, supplier_by_code, supplier_by_name = build_supplier_indexes(db)
    existing_pos = {po.orderpro_id: po for po in db.query(OrderProPurchaseOrder).all()}
    created = updated = unchanged = lines_created = lines_updated = lines_unchanged = 0
    missing_products = []
    missing_suppliers = []
    quantity_warnings = []
    quantities = quantity_report(purchase_orders)

    for row in purchase_orders:
        orderpro_id = clean_text(row.get("id"))
        if not orderpro_id:
            continue
        supplier, _supplier_method = resolve_purchase_order_supplier(
            row,
            supplier_by_orderpro_id=supplier_by_id,
            supplier_by_code=supplier_by_code,
            supplier_by_unique_name=supplier_by_name,
        )
        if supplier is None:
            missing_suppliers.append({"orderpro_id": orderpro_id, "supplier_name": purchase_order_supplier_name(row)})
        desired = desired_purchase_order_fields(row, supplier, sync_time)
        po = existing_pos.get(orderpro_id)
        if po is None:
            po = OrderProPurchaseOrder(**desired, created_at=sync_time)
            db.add(po)
            db.flush()
            existing_pos[orderpro_id] = po
            created += 1
        else:
            changes = changed_fields(po, desired)
            if changes:
                for field, value in desired.items():
                    setattr(po, field, value)
                updated += 1
            else:
                unchanged += 1

        existing_lines = {line.orderpro_line_key: line for line in po.lines}
        for index, item in enumerate(extract_purchase_order_items(row), start=1):
            product, _product_method = resolve_purchase_order_product(
                item,
                product_by_orderpro_id=product_by_id,
                product_by_sku=product_by_sku,
                product_by_unique_barcode=product_by_barcode,
                ambiguous_barcodes=ambiguous_barcodes,
            )
            if product is None:
                missing_products.append({"orderpro_id": orderpro_id, "sku": purchase_order_line_sku(item), "barcode": purchase_order_line_barcode(item)})
            desired_line, warnings = desired_purchase_order_line_fields(
                row,
                item,
                index=index,
                product=product,
                synced_at=sync_time,
            )
            quantity_warnings.extend(warnings)
            line = existing_lines.get(desired_line["orderpro_line_key"])
            if line is None:
                line = OrderProPurchaseOrderLine(orderpro_purchase_order_id=po.id, **desired_line, created_at=sync_time)
                db.add(line)
                db.flush()
                existing_lines[line.orderpro_line_key] = line
                lines_created += 1
            else:
                changes = changed_fields(line, desired_line)
                if changes:
                    for field, value in desired_line.items():
                        setattr(line, field, value)
                    lines_updated += 1
                else:
                    lines_unchanged += 1

    return {
        "mode": "apply",
        "summary": {
            "purchase_orders_created": created,
            "purchase_orders_updated": updated,
            "purchase_orders_unchanged": unchanged,
            "purchase_order_lines_created": lines_created,
            "purchase_order_lines_updated": lines_updated,
            "purchase_order_lines_unchanged": lines_unchanged,
            "items_missing_product_match": len(missing_products),
            "headers_missing_supplier_match": len(missing_suppliers),
            "quantity_warning_count": sum(quantities["warning_counts_by_type"].values()),
            "included_open_quantity_total": quantities["included_open_quantity_total"],
            "quantity_field_coverage": quantities["quantity_field_coverage"],
            "open_quantity_by_status": quantities["open_quantity_by_status"],
            "excluded_quantity_by_status": quantities["excluded_quantity_by_status"],
            "warning_counts_by_type": quantities["warning_counts_by_type"],
        },
        "report_notes": quantities["report_notes"],
        "line_samples_by_status": quantities["line_samples_by_status"],
        "sample_open_lines": quantities["sample_open_lines"],
        "sample_received_lines": quantities["sample_received_lines"],
        "items_missing_product_match_sample": missing_products[:10],
        "headers_missing_supplier_match_sample": missing_suppliers[:10],
        "quantity_warnings_sample": quantity_warnings[:10],
        "warnings": [],
    }


def fetch_orderpro_purchase_orders(client: OrderProClient, *, limit_pages: int | None = None) -> list[dict[str, Any]]:
    return fetch_orderpro_records_with_status(client, "/purchase-orders", limit_pages=limit_pages).records
