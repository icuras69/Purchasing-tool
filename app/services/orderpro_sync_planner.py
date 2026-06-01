from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.inventory_position import InventoryPosition
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services.orderpro_client import OrderProClient, extract_records, next_page_number


PRODUCT_FIELDS = (
    "name",
    "description",
    "barcode",
    "brand",
    "category",
    "uom",
    "weight_kg",
    "cost_price",
    "sell_price",
    "hs_code",
    "country_of_origin",
    "image_url",
    "is_active",
)

PRODUCT_FIELD_LIMITS = {
    "source_key": 255,
    "orderpro_id": 100,
    "orderpro_sku": 255,
    "supplier_sku": 255,
    "name": 255,
    "barcode": 255,
    "brand": 255,
    "category": 255,
    "uom": 50,
    "hs_code": 100,
    "country_of_origin": 100,
    "source_system": 50,
}


@dataclass
class OrderProFetchResult:
    records: list[dict[str, Any]]
    pages_fetched: int
    truncated_by_limit: bool


def fetch_orderpro_records(
    client: OrderProClient,
    path: str,
    *,
    limit_pages: int | None = None,
) -> list[dict[str, Any]]:
    return fetch_orderpro_records_with_status(client, path, limit_pages=limit_pages).records


def fetch_orderpro_records_with_status(
    client: OrderProClient,
    path: str,
    *,
    limit_pages: int | None = None,
) -> OrderProFetchResult:
    page = 1
    records: list[dict[str, Any]] = []
    pages_fetched = 0

    while True:
        payload = client.generic_get(path, params={"page": page})
        pages_fetched += 1
        records.extend(record for record in extract_records(payload) if isinstance(record, dict))

        next_page = next_page_number(payload, current_page=page)
        if limit_pages is not None and page >= limit_pages:
            return OrderProFetchResult(
                records=records,
                pages_fetched=pages_fetched,
                truncated_by_limit=next_page is not None,
            )
        if next_page is None:
            break
        page = next_page

    return OrderProFetchResult(records=records, pages_fetched=pages_fetched, truncated_by_limit=False)


def load_product_csv(path: str | Path) -> dict[str, dict[str, Any]]:
    csv_path = Path(path)
    rows_by_sku: dict[str, dict[str, Any]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            sku = clean_text(row.get("sku"))
            if sku:
                rows_by_sku[sku] = row
    return rows_by_sku


def plan_orderpro_sync(
    db: Session,
    *,
    suppliers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    product_csv_rows: dict[str, dict[str, Any]],
    inventory: list[dict[str, Any]] | None = None,
    supplier_pages_limited: bool = False,
) -> dict[str, Any]:
    supplier_plan = plan_supplier_sync(db, suppliers)
    product_plan = plan_product_sync(
        db,
        products,
        product_csv_rows,
        suppliers,
        supplier_pages_limited=supplier_pages_limited,
    )
    inventory_plan = (
        plan_inventory_sync(db, inventory or [], planned_products=products)
        if inventory is not None
        else inventory_not_requested()
    )

    return {
        "mode": "dry_run",
        "suppliers": supplier_plan,
        "products": product_plan,
        "inventory": inventory_plan,
        "warnings": [
            *supplier_plan["warnings"],
            *product_plan["warnings"],
            *inventory_plan["warnings"],
        ],
        "next_recommended_step": (
            "Review unknown CSV supplier_code values and missing product CSV rows before enabling any write sync."
        ),
    }


def apply_orderpro_supplier_product_sync(
    db: Session,
    *,
    suppliers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    product_csv_rows: dict[str, dict[str, Any]],
    inventory: list[dict[str, Any]] | None = None,
    mark_missing_inactive: bool = False,
    synced_at: datetime | None = None,
) -> dict[str, Any]:
    sync_time = synced_at or datetime.now(timezone.utc)
    supplier_result = apply_supplier_sync(db, suppliers, synced_at=sync_time)
    db.flush()
    product_result = apply_product_sync(
        db,
        products,
        product_csv_rows,
        suppliers,
        mark_missing_inactive=mark_missing_inactive,
        synced_at=sync_time,
    )
    db.flush()
    inventory_result = apply_inventory_sync(db, inventory, synced_at=sync_time) if inventory is not None else inventory_not_requested()
    db.flush()

    warnings = [*supplier_result["warnings"], *product_result["warnings"]]
    if inventory is not None:
        warnings.extend(inventory_result["warnings"])

    report = {
        "mode": "apply",
        "suppliers": supplier_result,
        "products": product_result,
        "warnings": warnings,
    }
    if inventory is not None:
        report["inventory"] = inventory_result
    return report


def apply_inventory_sync(
    db: Session,
    inventory: list[dict[str, Any]],
    *,
    synced_at: datetime,
) -> dict[str, Any]:
    sync_time = sync_time_without_timezone(synced_at)
    product_by_orderpro_id = {
        str(row.orderpro_id): row
        for row in db.query(Product).all()
        if row.orderpro_id
    }
    product_by_sku = {
        row.orderpro_sku: row
        for row in db.query(Product).all()
        if row.orderpro_sku
    }
    warehouse_by_orderpro_id = {
        str(row.orderpro_id): row
        for row in db.query(Warehouse).all()
        if row.orderpro_id
    }
    position_keys = {
        (row.product_id, row.warehouse_id, row.location_id, row.lot_id): row
        for row in db.query(InventoryPosition).all()
    }

    warehouses_created = []
    warehouses_updated = []
    positions_created = []
    positions_updated = []
    rows_missing_product = []
    rows_missing_warehouse = []
    current_stock_by_product_id: dict[int, float] = defaultdict(float)

    for row in inventory:
        orderpro_product_id = clean_text(row.get("product_id"))
        product_payload = row.get("product") if isinstance(row.get("product"), dict) else {}
        nested_sku = clean_text(product_payload.get("sku"))
        product = (product_by_orderpro_id.get(orderpro_product_id) if orderpro_product_id else None) or (
            product_by_sku.get(nested_sku) if nested_sku else None
        )
        if product is None:
            rows_missing_product.append(inventory_identity(row))
            continue

        warehouse_orderpro_id = clean_text(row.get("warehouse_id"))
        if not warehouse_orderpro_id:
            rows_missing_warehouse.append(inventory_identity(row))
            continue

        desired_warehouse = desired_warehouse_fields(row)
        desired_warehouse["last_synced_at"] = sync_time
        warehouse = warehouse_by_orderpro_id.get(warehouse_orderpro_id)
        if warehouse is None:
            warehouse = Warehouse(**desired_warehouse)
            db.add(warehouse)
            db.flush()
            warehouse_by_orderpro_id[warehouse_orderpro_id] = warehouse
            warehouses_created.append({"local_id": warehouse.id, "orderpro_id": warehouse_orderpro_id})
        else:
            changes = changed_fields(warehouse, desired_warehouse)
            if changes:
                for field, value in desired_warehouse.items():
                    setattr(warehouse, field, value)
                warehouses_updated.append({"local_id": warehouse.id, "orderpro_id": warehouse_orderpro_id, "changed_fields": sorted(changes)})

        quantity = to_float(row.get("qty"))
        current_stock_by_product_id[product.id] += quantity
        location_id_value = clean_text(row.get("location_id"))
        lot_id_value = clean_text(row.get("lot_id"))
        position_key = (product.id, warehouse.id, location_id_value, lot_id_value)
        desired_position = {
            "product_id": product.id,
            "warehouse_id": warehouse.id,
            "orderpro_inventory_id": clean_text(row.get("id")),
            "orderpro_product_id": orderpro_product_id,
            "orderpro_warehouse_id": warehouse_orderpro_id,
            "source_system": "orderpro",
            "location_id": location_id_value,
            "location_name": location_name(row),
            "lot_id": lot_id_value,
            "lot": clean_text(row.get("lot")),
            "quantity_on_hand": quantity,
            "quantity_available": quantity,
            "on_hand": quantity,
            "available": quantity,
            "last_synced_at": sync_time,
        }
        position = position_keys.get(position_key)
        if position is None:
            position = InventoryPosition(**desired_position)
            db.add(position)
            db.flush()
            position_keys[position_key] = position
            positions_created.append({"local_id": position.id, "product_id": product.id, "warehouse_id": warehouse.id})
        else:
            changes = changed_fields(position, desired_position)
            if changes:
                for field, value in desired_position.items():
                    setattr(position, field, value)
                positions_updated.append({"local_id": position.id, "changed_fields": sorted(changes)})

    products_current_stock_updated = []
    for product_id, total_stock in current_stock_by_product_id.items():
        product = db.get(Product, product_id)
        if product is not None and normalize_compare_value(product.current_stock) != normalize_compare_value(total_stock):
            product.current_stock = total_stock
            products_current_stock_updated.append({"product_id": product_id, "current_stock": total_stock})

    warnings = []
    if rows_missing_product:
        warnings.append(f"{len(rows_missing_product)} inventory rows could not be matched to local products.")
    if rows_missing_warehouse:
        warnings.append(f"{len(rows_missing_warehouse)} inventory rows were missing warehouse_id.")

    return {
        "summary": {
            "orderpro_inventory_rows": len(inventory),
            "warehouses_created": len(warehouses_created),
            "warehouses_updated": len(warehouses_updated),
            "inventory_positions_created": len(positions_created),
            "inventory_positions_updated": len(positions_updated),
            "rows_missing_product_match": len(rows_missing_product),
            "rows_missing_warehouse_id": len(rows_missing_warehouse),
            "products_current_stock_updated": len(products_current_stock_updated),
        },
        "warehouses_created": warehouses_created,
        "warehouses_updated": warehouses_updated,
        "inventory_positions_created": positions_created,
        "inventory_positions_updated": positions_updated,
        "rows_missing_product_match": rows_missing_product,
        "rows_missing_product_match_sample": rows_missing_product[:10],
        "rows_missing_warehouse_id": rows_missing_warehouse,
        "rows_missing_warehouse_id_sample": rows_missing_warehouse[:10],
        "products_current_stock_updated": products_current_stock_updated,
        "warnings": warnings,
    }


def apply_supplier_sync(
    db: Session,
    suppliers: list[dict[str, Any]],
    *,
    synced_at: datetime,
) -> dict[str, Any]:
    local_suppliers = db.query(Supplier).all()
    by_orderpro_id = {str(row.orderpro_id): row for row in local_suppliers if row.orderpro_id}
    by_code = {row.orderpro_code: row for row in local_suppliers if row.orderpro_code}
    by_normalized_name = {
        normalize_name(row.normalized_name or row.name): row
        for row in local_suppliers
        if row.normalized_name or row.name
    }

    created = []
    updated = []
    unchanged = []
    linked_existing_by_name = []
    missing_identity = []

    for row in suppliers:
        orderpro_id = clean_text(row.get("id"))
        code = clean_text(row.get("code"))
        if not orderpro_id and not code:
            missing_identity.append({"name": clean_text(row.get("name"))})
            continue

        desired = desired_supplier_fields(row)
        desired["last_synced_at"] = sync_time_without_timezone(synced_at)
        local = (by_orderpro_id.get(orderpro_id) if orderpro_id else None) or (by_code.get(code) if code else None)
        matched_by_name = False
        if local is None:
            local = by_normalized_name.get(normalize_name(desired["name"]))
            matched_by_name = local is not None
        if local is None:
            local = Supplier(
                **desired,
                normalized_name=normalize_name(desired["name"]),
            )
            db.add(local)
            db.flush()
            created.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_code": code})
            if orderpro_id:
                by_orderpro_id[orderpro_id] = local
            if code:
                by_code[code] = local
            by_normalized_name[normalize_name(local.normalized_name or local.name)] = local
            continue

        desired = safe_supplier_update_fields(db, local, desired)
        changes = changed_fields(local, desired)
        if changes:
            for field, value in desired.items():
                setattr(local, field, value)
            local.normalized_name = normalize_name(local.name)
            update_row = {"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_code": code, "changed_fields": sorted(changes)}
            if matched_by_name:
                update_row["match_type"] = "name"
                linked_existing_by_name.append(update_row)
            updated.append(update_row)
            if orderpro_id:
                by_orderpro_id[orderpro_id] = local
            if code:
                by_code[code] = local
        else:
            unchanged.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_code": code})

    warnings = [f"{len(missing_identity)} supplier rows were skipped because both id and code were missing."] if missing_identity else []
    return {
        "summary": {
            "orderpro_suppliers": len(suppliers),
            "created": len(created),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "linked_existing_by_name": len(linked_existing_by_name),
            "missing_code_or_id": len(missing_identity),
        },
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "linked_existing_by_name": linked_existing_by_name,
        "missing_code_or_id": missing_identity,
        "warnings": warnings,
    }


def apply_product_sync(
    db: Session,
    products: list[dict[str, Any]],
    product_csv_rows: dict[str, dict[str, Any]],
    suppliers: list[dict[str, Any]],
    *,
    mark_missing_inactive: bool,
    synced_at: datetime,
) -> dict[str, Any]:
    local_products = db.query(Product).all()
    local_suppliers = db.query(Supplier).all()
    local_by_orderpro_id = {str(row.orderpro_id): row for row in local_products if row.orderpro_id}
    local_by_sku = {row.orderpro_sku: row for row in local_products if row.orderpro_sku}
    supplier_by_code = {row.orderpro_code: row for row in local_suppliers if row.orderpro_code}
    orderpro_supplier_codes = {clean_text(row.get("code")) for row in suppliers if clean_text(row.get("code"))}
    orderpro_product_ids = {clean_text(row.get("id")) for row in products if clean_text(row.get("id"))}
    orderpro_skus = {clean_text(row.get("sku")) for row in products if clean_text(row.get("sku"))}

    created = []
    updated = []
    unchanged = []
    missing_from_csv = []
    csv_missing_supplier_code = []
    unknown_supplier_codes = []
    field_limit_violations = []
    deactivated = []

    for row in products:
        orderpro_id = clean_text(row.get("id"))
        sku = clean_text(row.get("sku"))
        csv_row = product_csv_rows.get(sku or "")
        supplier_code = clean_text(csv_row.get("supplier_code")) if csv_row else None
        supplier_sku = clean_text(csv_row.get("supplier_sku")) if csv_row else None

        if not csv_row:
            missing_from_csv.append(product_identity(row))
        elif not supplier_code:
            csv_missing_supplier_code.append(product_identity(row))
        elif supplier_code not in orderpro_supplier_codes:
            unknown_supplier_codes.append({"sku": sku, "supplier_code": supplier_code})

        local_supplier = supplier_by_code.get(supplier_code) if supplier_code in orderpro_supplier_codes else None
        desired = desired_product_fields(
            row,
            supplier_sku=supplier_sku,
            local_supplier_id=local_supplier.id if local_supplier else None,
        )
        desired["last_synced_at"] = sync_time_without_timezone(synced_at)
        violations = product_field_limit_violations(row, desired)
        if violations:
            field_limit_violations.extend(violations)
            continue
        local = (local_by_orderpro_id.get(orderpro_id) if orderpro_id else None) or (local_by_sku.get(sku) if sku else None)

        if local is None:
            local = Product(**desired)
            db.add(local)
            db.flush()
            created.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku})
            if orderpro_id:
                local_by_orderpro_id[orderpro_id] = local
            if sku:
                local_by_sku[sku] = local
            continue

        changes = changed_fields(local, desired)
        if changes:
            for field, value in desired.items():
                setattr(local, field, value)
            updated.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku, "changed_fields": sorted(changes)})
        else:
            unchanged.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku})

    if mark_missing_inactive:
        for product in db.query(Product).filter(Product.source_system == "orderpro").all():
            if product.orderpro_id and str(product.orderpro_id) in orderpro_product_ids:
                continue
            if product.orderpro_sku and product.orderpro_sku in orderpro_skus:
                continue
            if product.is_active:
                product.is_active = False
                product.last_synced_at = sync_time_without_timezone(synced_at)
                deactivated.append({"local_id": product.id, "orderpro_id": product.orderpro_id, "orderpro_sku": product.orderpro_sku})

    warnings = []
    if missing_from_csv:
        warnings.append(f"{len(missing_from_csv)} products were missing from the CSV export.")
    if csv_missing_supplier_code:
        warnings.append(f"{len(csv_missing_supplier_code)} CSV product rows were missing supplier_code.")
    if unknown_supplier_codes:
        warnings.append(f"{len(unknown_supplier_codes)} CSV supplier_code values were not found in OrderPro suppliers.")
    if field_limit_violations:
        warnings.append(f"{len(field_limit_violations)} product fields exceeded local column limits and were skipped.")

    return {
        "summary": {
            "orderpro_products": len(products),
            "created": len(created),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "missing_from_csv": len(missing_from_csv),
            "csv_rows_missing_supplier_code": len(csv_missing_supplier_code),
            "unknown_supplier_codes": len(unknown_supplier_codes),
            "field_limit_violations": len(field_limit_violations),
            "deactivated_missing_orderpro_products": len(deactivated),
            "mark_missing_inactive": mark_missing_inactive,
        },
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "missing_from_csv": missing_from_csv,
        "csv_rows_missing_supplier_code": csv_missing_supplier_code,
        "csv_rows_missing_supplier_code_sample": csv_missing_supplier_code[:10],
        "unknown_supplier_codes": unknown_supplier_codes,
        "field_limit_violations": field_limit_violations,
        "deactivated_missing_orderpro_products": deactivated,
        "warnings": warnings,
    }


def plan_supplier_sync(db: Session, suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    local_suppliers = db.query(Supplier).all()
    by_orderpro_id = {str(row.orderpro_id): row for row in local_suppliers if row.orderpro_id}
    by_code = {row.orderpro_code: row for row in local_suppliers if row.orderpro_code}
    by_normalized_name = {
        normalize_name(row.normalized_name or row.name): row
        for row in local_suppliers
        if row.normalized_name or row.name
    }
    orderpro_ids = {clean_text(row.get("id")) for row in suppliers if clean_text(row.get("id"))}
    orderpro_codes = {clean_text(row.get("code")) for row in suppliers if clean_text(row.get("code"))}

    to_create = []
    to_update = []
    matching = []
    matched_by_name = []
    missing_identity = []

    for row in suppliers:
        orderpro_id = clean_text(row.get("id"))
        code = clean_text(row.get("code"))
        if not orderpro_id and not code:
            missing_identity.append({"name": clean_text(row.get("name"))})
            continue

        desired = desired_supplier_fields(row)
        local = (by_orderpro_id.get(orderpro_id) if orderpro_id else None) or (by_code.get(code) if code else None)
        matched_by = "identity" if local is not None else None
        if local is None:
            local = by_normalized_name.get(normalize_name(desired["name"]))
            matched_by = "name" if local is not None else None
        if local is None:
            to_create.append(desired)
            continue

        changes = changed_fields(local, desired)
        if changes:
            update_row = {"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_code": code, "changes": changes}
            if matched_by == "name":
                update_row["match_type"] = "name"
                matched_by_name.append(update_row)
            to_update.append(update_row)
        else:
            matching.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_code": code})

    local_not_in_orderpro = [
        {"local_id": row.id, "name": row.name, "orderpro_id": row.orderpro_id, "orderpro_code": row.orderpro_code}
        for row in local_suppliers
        if (
            (row.orderpro_id and str(row.orderpro_id) not in orderpro_ids)
            or (row.orderpro_code and row.orderpro_code not in orderpro_codes)
        )
    ]

    return {
        "summary": {
            "orderpro_suppliers": len(suppliers),
            "to_create": len(to_create),
            "to_update": len(to_update),
            "already_matching": len(matching),
            "matched_by_name": len(matched_by_name),
            "linked_existing_by_name": len(matched_by_name),
            "missing_code_or_id": len(missing_identity),
            "local_not_found_in_orderpro": len(local_not_in_orderpro),
        },
        "to_create": to_create,
        "to_update": to_update,
        "already_matching": matching,
        "matched_by_name": matched_by_name,
        "missing_code_or_id": missing_identity,
        "local_not_found_in_orderpro": local_not_in_orderpro,
        "warnings": [f"{len(missing_identity)} supplier rows are missing both id and code."] if missing_identity else [],
    }


def plan_product_sync(
    db: Session,
    products: list[dict[str, Any]],
    product_csv_rows: dict[str, dict[str, Any]],
    suppliers: list[dict[str, Any]],
    *,
    supplier_pages_limited: bool = False,
) -> dict[str, Any]:
    local_products = db.query(Product).all()
    local_suppliers = db.query(Supplier).all()
    local_by_orderpro_id = {str(row.orderpro_id): row for row in local_products if row.orderpro_id}
    local_by_sku = {row.orderpro_sku: row for row in local_products if row.orderpro_sku}
    local_supplier_by_code = {row.orderpro_code: row for row in local_suppliers if row.orderpro_code}
    orderpro_supplier_codes = {clean_text(row.get("code")) for row in suppliers if clean_text(row.get("code"))}

    to_create = []
    to_update = []
    matching = []
    matched_by_orderpro_id = []
    matched_by_orderpro_sku = []
    missing_from_csv = []
    csv_missing_supplier_code = []
    unknown_supplier_codes = []
    unknown_supplier_code_samples: dict[str, list[str | None]] = defaultdict(list)
    field_limit_violations = []
    would_assign_supplier = []
    without_supplier = []

    for row in products:
        orderpro_id = clean_text(row.get("id"))
        sku = clean_text(row.get("sku"))
        csv_row = product_csv_rows.get(sku or "")
        supplier_code = clean_text(csv_row.get("supplier_code")) if csv_row else None
        supplier_sku = clean_text(csv_row.get("supplier_sku")) if csv_row else None

        if not csv_row:
            missing_from_csv.append(product_identity(row))
        elif not supplier_code:
            csv_missing_supplier_code.append(product_identity(row))
        elif supplier_code not in orderpro_supplier_codes:
            unknown_supplier_codes.append({"sku": sku, "supplier_code": supplier_code})
            if len(unknown_supplier_code_samples[supplier_code]) < 5:
                unknown_supplier_code_samples[supplier_code].append(sku)

        local_supplier = local_supplier_by_code.get(supplier_code) if supplier_code else None
        if supplier_code and supplier_code in orderpro_supplier_codes:
            would_assign_supplier.append({"sku": sku, "supplier_code": supplier_code, "local_supplier_id": local_supplier.id if local_supplier else None})
        else:
            without_supplier.append({"sku": sku, "reason": supplier_assignment_reason(csv_row, supplier_code, orderpro_supplier_codes)})

        local = local_by_orderpro_id.get(orderpro_id) if orderpro_id else None
        matched_by = "orderpro_id" if local is not None else None
        if local is None and sku:
            local = local_by_sku.get(sku)
            matched_by = "orderpro_sku" if local is not None else None
        desired = desired_product_fields(row, supplier_sku=supplier_sku, local_supplier_id=local_supplier.id if local_supplier else None)
        field_limit_violations.extend(product_field_limit_violations(row, desired))
        if local is None:
            to_create.append(desired)
            continue

        if matched_by == "orderpro_id":
            matched_by_orderpro_id.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku})
        elif matched_by == "orderpro_sku":
            matched_by_orderpro_sku.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku})

        changes = changed_fields(local, desired)
        if changes:
            to_update.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku, "changes": changes})
        else:
            matching.append({"local_id": local.id, "orderpro_id": orderpro_id, "orderpro_sku": sku})

    warnings = []
    if missing_from_csv:
        warnings.append(f"{len(missing_from_csv)} OrderPro products were missing from the CSV export.")
    if csv_missing_supplier_code:
        warnings.append(f"{len(csv_missing_supplier_code)} CSV product rows were missing supplier_code.")
    if unknown_supplier_codes:
        warnings.append(f"{len(unknown_supplier_codes)} CSV supplier_code values were not found in OrderPro suppliers.")
    if supplier_pages_limited and unknown_supplier_codes:
        warnings.append("Unknown supplier_code results may be unreliable because supplier API pages were limited.")
    if field_limit_violations:
        warnings.append(f"{len(field_limit_violations)} product fields exceeded local column limits and need review.")

    return {
        "summary": {
            "orderpro_products": len(products),
            "to_create": len(to_create),
            "to_update": len(to_update),
            "already_matching": len(matching),
            "matched_local_by_orderpro_id": len(matched_by_orderpro_id),
            "matched_local_by_orderpro_sku": len(matched_by_orderpro_sku),
            "missing_from_csv": len(missing_from_csv),
            "csv_rows_missing_supplier_code": len(csv_missing_supplier_code),
            "unknown_supplier_codes": len(unknown_supplier_codes),
            "field_limit_violations": len(field_limit_violations),
            "would_assign_supplier": len(would_assign_supplier),
            "would_remain_without_supplier": len(without_supplier),
            "unknown_supplier_code_check_used_full_supplier_list": not supplier_pages_limited,
        },
        "to_create": to_create,
        "to_update": to_update,
        "already_matching": matching,
        "matched_by_orderpro_id": matched_by_orderpro_id,
        "matched_by_orderpro_sku": matched_by_orderpro_sku,
        "missing_from_csv": missing_from_csv,
        "csv_rows_missing_supplier_code": csv_missing_supplier_code,
        "csv_rows_missing_supplier_code_sample": csv_missing_supplier_code[:10],
        "unknown_supplier_codes": unknown_supplier_codes,
        "unknown_supplier_code_samples": [
            {"supplier_code": code, "sample_skus": skus}
            for code, skus in sorted(unknown_supplier_code_samples.items())
        ],
        "field_limit_violations": field_limit_violations,
        "would_assign_supplier": would_assign_supplier,
        "would_remain_without_supplier": without_supplier,
        "would_remain_without_supplier_sample": without_supplier[:10],
        "warnings": warnings,
    }


def plan_inventory_sync(
    db: Session,
    inventory: list[dict[str, Any]],
    *,
    planned_products: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    local_products = db.query(Product).all()
    local_warehouses = db.query(Warehouse).all()
    local_positions = db.query(InventoryPosition).all()

    product_by_orderpro_id = {str(row.orderpro_id): row for row in local_products if row.orderpro_id}
    product_by_sku = {row.orderpro_sku: row for row in local_products if row.orderpro_sku}
    planned_product_by_orderpro_id = {
        clean_text(row.get("id")): row for row in (planned_products or []) if clean_text(row.get("id"))
    }
    planned_product_by_sku = {
        clean_text(row.get("sku")): row for row in (planned_products or []) if clean_text(row.get("sku"))
    }
    warehouse_by_orderpro_id = {str(row.orderpro_id): row for row in local_warehouses if row.orderpro_id}

    position_keys = {
        (row.product_id, row.warehouse_id, row.location_id, row.lot_id): row
        for row in local_positions
    }

    warehouses_to_create: dict[str, dict[str, Any]] = {}
    warehouses_to_update = []
    positions_to_create = []
    positions_to_update = []
    rows_missing_product = []
    rows_missing_warehouse = []
    rows_with_derivable_warehouse_missing_name = []
    stock_by_product: dict[str, float] = defaultdict(float)
    stock_by_orderpro_product_id: dict[str, float] = defaultdict(float)
    warehouse_updates_seen: set[str] = set()

    for row in inventory:
        orderpro_product_id = clean_text(row.get("product_id"))
        product_payload = row.get("product") if isinstance(row.get("product"), dict) else {}
        nested_sku = clean_text(product_payload.get("sku"))
        product = (product_by_orderpro_id.get(orderpro_product_id) if orderpro_product_id else None) or (
            product_by_sku.get(nested_sku) if nested_sku else None
        )
        warehouse_orderpro_id = clean_text(row.get("warehouse_id"))
        if not warehouse_orderpro_id:
            rows_missing_warehouse.append(inventory_identity(row))
            continue

        desired_warehouse = desired_warehouse_fields(row)
        if desired_warehouse["name"] == f"OrderPro Warehouse {warehouse_orderpro_id}":
            rows_with_derivable_warehouse_missing_name.append(inventory_identity(row))
        warehouse = warehouse_by_orderpro_id.get(warehouse_orderpro_id)
        if warehouse is None:
            warehouses_to_create.setdefault(warehouse_orderpro_id, desired_warehouse)
            warehouse_id_for_key = None
        else:
            changes = changed_fields(warehouse, desired_warehouse)
            if changes and warehouse_orderpro_id not in warehouse_updates_seen:
                warehouses_to_update.append({"local_id": warehouse.id, "orderpro_id": warehouse_orderpro_id, "changes": changes})
                warehouse_updates_seen.add(warehouse_orderpro_id)
            warehouse_id_for_key = warehouse.id

        planned_product = None
        if product is None:
            planned_product = (
                planned_product_by_orderpro_id.get(orderpro_product_id) if orderpro_product_id else None
            ) or (planned_product_by_sku.get(nested_sku) if nested_sku else None)
        if product is None and planned_product is None:
            rows_missing_product.append(inventory_identity(row))
            continue

        quantity = to_float(row.get("qty"))
        if product is not None:
            stock_by_product[str(product.id)] += quantity
        if orderpro_product_id:
            stock_by_orderpro_product_id[orderpro_product_id] += quantity
        position_key = (
            product.id if product is not None else None,
            warehouse_id_for_key,
            clean_text(row.get("location_id")),
            clean_text(row.get("lot_id")),
        )
        desired_position = {
            "product_id": product.id if product is not None else None,
            "planned_product": product is None and planned_product is not None,
            "warehouse_id": warehouse_id_for_key,
            "orderpro_product_id": orderpro_product_id,
            "orderpro_product_sku": nested_sku,
            "orderpro_warehouse_id": warehouse_orderpro_id,
            "location_id": clean_text(row.get("location_id")),
            "location_name": location_name(row),
            "lot_id": clean_text(row.get("lot_id")),
            "lot": clean_text(row.get("lot")),
            "quantity_on_hand": quantity,
            "quantity_available": quantity,
            "source_system": "orderpro",
        }
        local_position = position_keys.get(position_key)
        if local_position is None:
            positions_to_create.append(desired_position)
        else:
            changes = changed_fields(local_position, desired_position)
            if changes:
                positions_to_update.append({"local_id": local_position.id, "changes": changes})

    warnings = []
    if rows_missing_product:
        warnings.append(f"{len(rows_missing_product)} inventory rows could not be matched to local products.")
    if rows_missing_warehouse:
        warnings.append(f"{len(rows_missing_warehouse)} inventory rows were missing warehouse_id.")
    if rows_with_derivable_warehouse_missing_name:
        warnings.append(
            f"{len(rows_with_derivable_warehouse_missing_name)} inventory rows had warehouse_id but no warehouse name/object."
        )

    return {
        "summary": {
            "orderpro_inventory_rows": len(inventory),
            "warehouses_to_create": len(warehouses_to_create),
            "warehouses_to_update": len(warehouses_to_update),
            "inventory_positions_to_create": len(positions_to_create),
            "inventory_positions_to_update": len(positions_to_update),
            "rows_missing_product_match": len(rows_missing_product),
            "rows_missing_warehouse_id": len(rows_missing_warehouse),
            "rows_with_derivable_warehouse_missing_name": len(rows_with_derivable_warehouse_missing_name),
        },
        "warehouses_to_create": list(warehouses_to_create.values()),
        "warehouses_to_update": warehouses_to_update,
        "inventory_positions_to_create": positions_to_create,
        "inventory_positions_to_update": positions_to_update,
        "rows_missing_product_match": rows_missing_product,
        "rows_missing_warehouse_id": rows_missing_warehouse,
        "rows_with_derivable_warehouse_missing_name": rows_with_derivable_warehouse_missing_name,
        "total_stock_by_local_product_id": dict(stock_by_product),
        "total_stock_by_orderpro_product_id": dict(stock_by_orderpro_product_id),
        "warnings": warnings,
    }


def inventory_not_requested() -> dict[str, Any]:
    return {
        "summary": {"included": False},
        "warehouses_to_create": [],
        "warehouses_to_update": [],
        "inventory_positions_to_create": [],
        "inventory_positions_to_update": [],
        "rows_missing_product_match": [],
        "rows_missing_warehouse_id": [],
        "rows_with_derivable_warehouse_missing_name": [],
        "total_stock_by_local_product_id": {},
        "total_stock_by_orderpro_product_id": {},
        "warnings": [],
    }


def desired_supplier_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "orderpro_id": clean_text(row.get("id")),
        "orderpro_code": clean_text(row.get("code")),
        "name": clean_text(row.get("name")) or "Unnamed Supplier",
        "email": clean_text(row.get("email")),
        "phone": clean_text(row.get("phone")),
        "is_active": to_bool(row.get("is_active"), default=True),
        "source_system": "orderpro",
    }


def desired_product_fields(row: dict[str, Any], *, supplier_sku: str | None, local_supplier_id: int | None) -> dict[str, Any]:
    desired = {
        "orderpro_id": clean_text(row.get("id")),
        "orderpro_sku": clean_text(row.get("sku")),
        "source_key": clean_text(row.get("sku")),
        "source_system": "orderpro",
        "supplier_id": local_supplier_id,
        "supplier_sku": supplier_sku,
    }
    for field in PRODUCT_FIELDS:
        value = row.get(field)
        if field in {"weight_kg", "cost_price", "sell_price"}:
            desired[field] = to_float(value) if value not in (None, "") else None
        elif field == "is_active":
            desired[field] = to_bool(value, default=True)
        elif field in {"description", "image_url"}:
            desired[field] = clean_preserved_text(value)
        else:
            desired[field] = clean_text(value)
    desired["name"] = desired["name"] or clean_text(row.get("sku")) or "Unnamed Product"
    return desired


def product_field_limit_violations(row: dict[str, Any], desired: dict[str, Any]) -> list[dict[str, Any]]:
    sku = clean_text(row.get("sku")) or clean_text(desired.get("orderpro_sku"))
    violations = []
    for field, limit in PRODUCT_FIELD_LIMITS.items():
        value = desired.get(field)
        if isinstance(value, str) and len(value) > limit:
            violations.append(
                {
                    "orderpro_id": clean_text(row.get("id")),
                    "orderpro_sku": sku,
                    "field": field,
                    "limit": limit,
                    "actual_length": len(value),
                    "sample": value[:120],
                }
            )
    return violations


def desired_warehouse_fields(row: dict[str, Any]) -> dict[str, Any]:
    warehouse_payload = row.get("warehouse") if isinstance(row.get("warehouse"), dict) else {}
    warehouse_id = clean_text(row.get("warehouse_id"))
    name = (
        clean_text(warehouse_payload.get("name"))
        or clean_text(warehouse_payload.get("title"))
        or clean_text(row.get("warehouse"))
        or f"OrderPro Warehouse {warehouse_id}"
    )
    return {
        "orderpro_id": warehouse_id,
        "name": name,
        "code": clean_text(warehouse_payload.get("code")),
        "is_active": to_bool(warehouse_payload.get("is_active"), default=True),
        "source_system": "orderpro",
    }


def changed_fields(model: Any, desired: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changes = {}
    for field, desired_value in desired.items():
        current_value = getattr(model, field, None)
        if normalize_compare_value(current_value) != normalize_compare_value(desired_value):
            changes[field] = {"current": current_value, "desired": desired_value}
    return changes


def safe_supplier_update_fields(db: Session, supplier: Supplier, desired: dict[str, Any]) -> dict[str, Any]:
    safe = dict(desired)
    desired_name = clean_text(safe.get("name"))
    if desired_name and desired_name != supplier.name:
        existing = db.query(Supplier).filter(Supplier.name == desired_name, Supplier.id != supplier.id).first()
        if existing is not None:
            safe.pop("name", None)
    return safe


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_preserved_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def to_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "active"}:
        return True
    if text in {"0", "false", "no", "n", "inactive"}:
        return False
    return default


def to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_compare_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def product_identity(row: dict[str, Any]) -> dict[str, Any]:
    return {"orderpro_id": clean_text(row.get("id")), "sku": clean_text(row.get("sku")), "name": clean_text(row.get("name"))}


def inventory_identity(row: dict[str, Any]) -> dict[str, Any]:
    product_payload = row.get("product") if isinstance(row.get("product"), dict) else {}
    return {
        "product_id": clean_text(row.get("product_id")),
        "product_sku": clean_text(product_payload.get("sku")),
        "warehouse_id": clean_text(row.get("warehouse_id")),
        "location_id": clean_text(row.get("location_id")),
        "lot_id": clean_text(row.get("lot_id")),
    }


def supplier_assignment_reason(
    csv_row: dict[str, Any] | None,
    supplier_code: str | None,
    orderpro_supplier_codes: set[str | None],
) -> str:
    if not csv_row:
        return "missing_csv_row"
    if not supplier_code:
        return "csv_missing_supplier_code"
    if supplier_code not in orderpro_supplier_codes:
        return "supplier_code_not_found_in_orderpro"
    return "local_supplier_not_found"


def location_name(row: dict[str, Any]) -> str | None:
    location = row.get("location")
    if isinstance(location, dict):
        return clean_text(location.get("name")) or clean_text(location.get("title"))
    return clean_text(location)


def normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()


def sync_time_without_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
