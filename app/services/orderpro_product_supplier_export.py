from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier
from app.services.supplier_identity import normalize_supplier_name


PRODUCT_ID_COLUMNS = {"id", "product_id", "orderpro_id", "orderpro_product_id"}
SKU_COLUMNS = {"sku", "product_sku", "orderpro_sku"}
BARCODE_COLUMNS = {"barcode", "ean", "upc"}
NAME_COLUMNS = {"name", "product_name"}
SUPPLIER_CODE_COLUMNS = {"supplier_code", "supplier", "supplier_ref"}
SUPPLIER_ID_COLUMNS = {"supplier_id", "orderpro_supplier_id"}
SUPPLIER_NAME_COLUMNS = {"supplier_name"}
SUPPLIER_SKU_COLUMNS = {"supplier_sku", "supplier_product_code"}
LEAD_TIME_COLUMNS = {"lead_time", "lead_time_days", "leadtime"}
COST_PRICE_COLUMNS = {"cost_price", "cost", "purchase_price", "unit_cost"}
MOQ_COLUMNS = {"min_order_qty", "minimum_order_quantity", "moq"}


@dataclass
class ProductSupplierExportPlan:
    mode: str
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    records_created: int = 0
    records_updated: int = 0
    products_confirmed: int = 0
    lead_times_applied: int = 0
    cost_prices_applied: int = 0
    moqs_applied: int = 0


def normalize_column_name(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_code(value: Any) -> str | None:
    text = normalize_text(value)
    return text.upper() if text else None


def normalize_name(value: Any) -> str | None:
    return normalize_supplier_name(value)


def read_export_rows(path: str | Path, *, limit: int | None = None) -> list[dict[str, str | None]]:
    file_path = Path(path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return _read_excel_rows(file_path, limit=limit)
    return _read_csv_rows(file_path, limit=limit)


def _read_csv_rows(path: Path, *, limit: int | None) -> list[dict[str, str | None]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            rows.append({normalize_column_name(key or ""): normalize_text(value) for key, value in row.items()})
        return rows


def _read_excel_rows(path: Path, *, limit: int | None) -> list[dict[str, str | None]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Excel import requires pandas with an Excel engine installed.") from exc
    frame = pd.read_excel(path, dtype=str)
    if limit is not None:
        frame = frame.head(limit)
    normalized_columns = {column: normalize_column_name(str(column)) for column in frame.columns}
    return [
        {
            normalized_columns[column]: normalize_text(value)
            for column, value in row.items()
            if not (hasattr(pd, "isna") and pd.isna(value))
        }
        for row in frame.to_dict(orient="records")
    ]


def normalize_export_row(row: dict[str, Any]) -> dict[str, str | None]:
    normalized = {normalize_column_name(key): normalize_text(value) for key, value in row.items()}
    return {
        "orderpro_product_id": _first_value(normalized, PRODUCT_ID_COLUMNS),
        "sku": _first_value(normalized, SKU_COLUMNS),
        "barcode": _first_value(normalized, BARCODE_COLUMNS),
        "product_name": _first_value(normalized, NAME_COLUMNS),
        "supplier_code": _first_value(normalized, SUPPLIER_CODE_COLUMNS),
        "supplier_orderpro_id": _first_value(normalized, SUPPLIER_ID_COLUMNS),
        "supplier_name": _first_value(normalized, SUPPLIER_NAME_COLUMNS),
        "supplier_sku": _first_value(normalized, SUPPLIER_SKU_COLUMNS),
        "lead_time_days": _first_value(normalized, LEAD_TIME_COLUMNS),
        "cost_price": _first_value(normalized, COST_PRICE_COLUMNS),
        "min_order_qty": _first_value(normalized, MOQ_COLUMNS),
    }


def _first_value(row: dict[str, str | None], names: set[str]) -> str | None:
    for name in names:
        value = row.get(name)
        if value:
            return value
    return None


def plan_orderpro_product_supplier_export(
    db: Session,
    path: str | Path,
    *,
    limit: int | None = None,
) -> ProductSupplierExportPlan:
    raw_rows = read_export_rows(path, limit=limit)
    normalized_rows = [normalize_export_row(row) for row in raw_rows]
    header_diagnostics = _header_diagnostics(raw_rows)
    product_lookup = _build_product_lookup(db)
    supplier_lookup = _build_supplier_lookup(db)
    rows = [
        _plan_row(db, row, row_number=index + 1, product_lookup=product_lookup, supplier_lookup=supplier_lookup)
        for index, row in enumerate(normalized_rows)
    ]
    return ProductSupplierExportPlan(
        mode="dry-run",
        summary=_summarize_rows(db, rows, header_diagnostics, product_lookup.get("diagnostics")),
        rows=rows,
    )


def apply_orderpro_product_supplier_export(
    db: Session,
    path: str | Path,
    *,
    apply_suggestions: bool = False,
    confirm_exact_code: bool = False,
    limit: int | None = None,
) -> ProductSupplierExportPlan:
    if not apply_suggestions and not confirm_exact_code:
        return plan_orderpro_product_supplier_export(db, path, limit=limit)

    plan = plan_orderpro_product_supplier_export(db, path, limit=limit)
    created = 0
    updated = 0
    confirmed = 0
    lead_times_applied = 0
    cost_prices_applied = 0
    moqs_applied = 0
    now = datetime.utcnow()
    for row in plan.rows:
        product_id = row.get("product_id")
        if not product_id or not row.get("supplier_id"):
            continue
        if row["classification"] not in {"suggestion", "confirm_candidate", "existing_same_supplier"}:
            continue
        product = db.get(Product, product_id)
        if product is None:
            continue
        review = product.supplier_assignment_review
        if review is None:
            review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
            db.add(review)
            created += 1
        else:
            updated += 1
        _apply_row_to_review(review, row)
        if confirm_exact_code and row["can_apply_verified_inputs"]:
            if product.supplier_id is None or product.supplier_id == row["supplier_id"]:
                if product.supplier_id is None:
                    confirmed += 1
                product.supplier_id = row["supplier_id"]
                product.supplier_sku = row["supplier_sku"] or product.supplier_sku
                lead_time_days = positive_int(row.get("lead_time_days"), maximum=365)
                if lead_time_days is not None and product.lead_time_days != lead_time_days:
                    product.lead_time_days = lead_time_days
                    lead_times_applied += 1
                cost_price = positive_float(row.get("cost_price"))
                if cost_price is not None and product.cost_price != cost_price:
                    product.cost_price = cost_price
                    cost_prices_applied += 1
                min_order_qty = positive_float(row.get("min_order_qty"))
                if min_order_qty is not None and product.min_order_qty != min_order_qty:
                    product.min_order_qty = min_order_qty
                    moqs_applied += 1
                review.status = "confirmed"
                review.reviewed_supplier_id = row["supplier_id"]
                review.reviewed_by = "orderpro_product_export"
                review.reviewed_at = now
    db.commit()
    plan.mode = "apply"
    plan.records_created = created
    plan.records_updated = updated
    plan.products_confirmed = confirmed
    plan.lead_times_applied = lead_times_applied
    plan.cost_prices_applied = cost_prices_applied
    plan.moqs_applied = moqs_applied
    raw_rows = read_export_rows(path, limit=limit)
    product_lookup = _build_product_lookup(db)
    plan.summary = _summarize_rows(db, plan.rows, _header_diagnostics(raw_rows), product_lookup.get("diagnostics"))
    plan.summary["review_suggestions_created"] = created
    plan.summary["review_suggestions_updated"] = updated
    plan.summary["products_confirmed"] = confirmed
    plan.summary["lead_times_applied"] = lead_times_applied
    plan.summary["cost_prices_applied"] = cost_prices_applied
    plan.summary["moqs_applied"] = moqs_applied
    return plan


def _apply_row_to_review(review: ProductSupplierAssignmentReview, row: dict[str, Any]) -> None:
    review.suggested_supplier_id = row["supplier_id"]
    review.suggestion_source = "orderpro_product_export"
    review.confidence_label = row["confidence_label"]
    review.confidence_score = row["confidence_score"]
    review.status = "suggested"
    review.evidence_summary = row["evidence_summary"]
    review.warnings = row["warnings"]
    review.updated_at = datetime.utcnow()


def _build_product_lookup(db: Session) -> dict[str, Any]:
    products = db.query(Product).all()
    orderpro_products = [product for product in products if _is_current_orderpro_product(product)]
    by_orderpro_id = {
        str(product.orderpro_id): product
        for product in orderpro_products
        if normalize_code(product.orderpro_id)
    }
    orderpro_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    global_by_sku: dict[str, list[Product]] = defaultdict(list)
    legacy_by_sku: dict[str, list[Product]] = defaultdict(list)
    orderpro_products_with_blank_sku = 0
    for product in orderpro_products:
        sku_entries = _current_orderpro_sku_entries(product)
        if not sku_entries:
            orderpro_products_with_blank_sku += 1
        for field_name, code in sku_entries:
            orderpro_by_sku[code].append({"product": product, "field": field_name})
    for product in products:
        for value in _global_sku_values(product):
            code = normalize_code(value)
            if code:
                global_by_sku[code].append(product)
                if not _is_current_orderpro_product(product):
                    legacy_by_sku[code].append(product)
    orderpro_barcode_groups: dict[str, list[Product]] = defaultdict(list)
    global_barcode_groups: dict[str, list[Product]] = defaultdict(list)
    orderpro_products_with_blank_barcode = 0
    for product in orderpro_products:
        code = normalize_code(product.barcode)
        if code:
            orderpro_barcode_groups[code].append(product)
        else:
            orderpro_products_with_blank_barcode += 1
    for product in products:
        code = normalize_code(product.barcode)
        if code:
            global_barcode_groups[code].append(product)
    duplicate_orderpro_sku_keys = {
        key: values
        for key, values in orderpro_by_sku.items()
        if len({entry["product"].id for entry in values}) > 1
    }
    duplicate_orderpro_barcode_keys = {
        key: values
        for key, values in orderpro_barcode_groups.items()
        if len(values) > 1
    }
    return {
        "by_orderpro_id": by_orderpro_id,
        "orderpro_by_sku": orderpro_by_sku,
        "global_by_sku": global_by_sku,
        "legacy_by_sku": legacy_by_sku,
        "orderpro_unique_barcodes": {
            key: values[0] for key, values in orderpro_barcode_groups.items() if len(values) == 1
        },
        "orderpro_duplicate_barcodes": set(duplicate_orderpro_barcode_keys),
        "global_barcode_groups": global_barcode_groups,
        "diagnostics": {
            "blank_orderpro_product_sku_count": orderpro_products_with_blank_sku,
            "blank_orderpro_product_barcode_count": orderpro_products_with_blank_barcode,
            "nonblank_orderpro_sku_key_count": len(orderpro_by_sku),
            "nonblank_orderpro_barcode_key_count": len(orderpro_barcode_groups),
            "duplicate_orderpro_sku_key_count": len(duplicate_orderpro_sku_keys),
            "duplicate_orderpro_barcode_key_count": len(duplicate_orderpro_barcode_keys),
            "duplicate_orderpro_sku_keys_sample": [
                {"key": key, "product_ids": [entry["product"].id for entry in values[:5]]}
                for key, values in list(duplicate_orderpro_sku_keys.items())[:10]
            ],
            "duplicate_orderpro_barcode_keys_sample": [
                {"key": key, "product_ids": [product.id for product in values[:5]]}
                for key, values in list(duplicate_orderpro_barcode_keys.items())[:10]
            ],
        },
    }


def _current_orderpro_sku_entries(product: Product) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    product_sku = normalize_code(getattr(product, "sku", None))
    if product_sku:
        entries.append(("product_sku", product_sku))
    orderpro_sku = normalize_code(product.orderpro_sku)
    if orderpro_sku:
        entries.append(("product_orderpro_sku", orderpro_sku))
    return entries


def _global_sku_values(product: Product) -> list[Any]:
    values: list[Any] = [getattr(product, "sku", None), product.orderpro_sku]
    if not _is_current_orderpro_product(product):
        values.append(product.source_key)
    return values


def _is_current_orderpro_product(product: Product) -> bool:
    return bool(
        product.source_system == "orderpro"
        or product.orderpro_id is not None
        or product.orderpro_sku is not None
    )


def _build_supplier_lookup(db: Session) -> dict[str, Any]:
    suppliers = db.query(Supplier).all()
    by_orderpro_id = {str(supplier.orderpro_id): supplier for supplier in suppliers if supplier.orderpro_id}
    by_code = {normalize_code(supplier.orderpro_code): supplier for supplier in suppliers if supplier.orderpro_code}
    name_groups: dict[str, list[Supplier]] = defaultdict(list)
    for supplier in suppliers:
        name = normalize_name(supplier.name)
        if name:
            name_groups[name].append(supplier)
    return {
        "by_orderpro_id": by_orderpro_id,
        "by_code": by_code,
        "unique_names": {key: values[0] for key, values in name_groups.items() if len(values) == 1},
        "duplicate_names": {key for key, values in name_groups.items() if len(values) > 1},
    }


def _plan_row(
    db: Session,
    row: dict[str, str | None],
    *,
    row_number: int,
    product_lookup: dict[str, Any],
    supplier_lookup: dict[str, Any],
) -> dict[str, Any]:
    product, product_method, product_warning = _match_product(row, product_lookup)
    supplier, supplier_method, supplier_warning = _match_supplier(row, supplier_lookup)
    product_match_diagnostic = _product_match_diagnostic(row, product_lookup, product_method)
    product_sku_matched_field = _product_sku_matched_field(row, product_lookup, product)
    warnings = [warning for warning in (product_warning, supplier_warning) if warning]
    valid = bool((row["orderpro_product_id"] or row["sku"] or row["barcode"]) and (row["supplier_code"] or row["supplier_orderpro_id"] or row["supplier_name"]))
    classification = "invalid"
    can_confirm = False
    confidence_label = "none"
    confidence_score = 0.0
    if valid and product and supplier:
        product_exact = product_method in {"orderpro_id", "sku", "unique_barcode"}
        supplier_exact = supplier_method in {"supplier_code", "supplier_orderpro_id"}
        if product.supplier_id == supplier.id:
            classification = "existing_same_supplier"
            confidence_label = "high"
            confidence_score = 1.0
        elif product.supplier_id and product.supplier_id != supplier.id:
            classification = "existing_supplier_conflict"
            warnings.append("Product already has a different supplier_id; not overwriting.")
        elif product_exact and supplier_exact:
            classification = "confirm_candidate"
            can_confirm = True
            confidence_label = "high"
            confidence_score = 0.98
        elif supplier_method == "unique_name":
            classification = "suggestion"
            confidence_label = "medium"
            confidence_score = 0.6
            warnings.append("Supplier matched by exact unique name only; review required.")
        else:
            classification = "suggestion"
            confidence_label = "medium"
            confidence_score = 0.7
    elif valid and product and not supplier:
        classification = "unmatched_supplier"
    elif valid and supplier and not product:
        classification = "unmatched_product"
    elif valid:
        classification = "unmatched_product_and_supplier"

    evidence = {
        "source": "orderpro_product_export",
        "row_number": row_number,
        "orderpro_product_id": row["orderpro_product_id"],
        "sku": row["sku"],
        "barcode": row["barcode"],
        "product_name": row["product_name"],
        "supplier_code": row["supplier_code"],
        "supplier_orderpro_id": row["supplier_orderpro_id"],
        "supplier_name": row["supplier_name"],
        "supplier_sku": row["supplier_sku"],
        "lead_time_days": row["lead_time_days"],
        "cost_price": row["cost_price"],
        "min_order_qty": row["min_order_qty"],
        "product_match_method": product_method,
        "product_match_diagnostic": product_match_diagnostic,
        "product_sku_matched_field": product_sku_matched_field,
        "supplier_match_method": supplier_method,
    }
    return {
        "row_number": row_number,
        "valid": valid,
        "classification": classification,
        "product_id": product.id if product else None,
        "product_name": product.name if product else row["product_name"],
        "orderpro_sku": product.orderpro_sku if product else row["sku"],
        "product_match_method": product_method,
        "product_match_diagnostic": product_match_diagnostic,
        "product_sku_matched_field": product_sku_matched_field,
        "supplier_id": supplier.id if supplier else None,
        "supplier_name": supplier.name if supplier else row["supplier_name"],
        "supplier_match_method": supplier_method,
        "supplier_sku": row["supplier_sku"],
        "lead_time_days": row["lead_time_days"],
        "cost_price": row["cost_price"],
        "min_order_qty": row["min_order_qty"],
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "can_confirm_exact_code": can_confirm,
        "can_apply_verified_inputs": bool(
            valid
            and product
            and supplier
            and product_method in {"orderpro_id", "sku", "unique_barcode"}
            and supplier_method in {"supplier_code", "supplier_orderpro_id"}
            and product.supplier_id in {None, supplier.id}
        ),
        "evidence_summary": evidence,
        "warnings": warnings,
    }


def _match_product(row: dict[str, str | None], lookup: dict[str, Any]) -> tuple[Product | None, str | None, str | None]:
    if row["orderpro_product_id"]:
        product = lookup["by_orderpro_id"].get(str(row["orderpro_product_id"]))
        if product:
            return product, "orderpro_id", None
    sku = normalize_code(row["sku"])
    if sku:
        orderpro_entries = lookup["orderpro_by_sku"].get(sku, [])
        orderpro_products = _unique_products_from_sku_entries(orderpro_entries)
        global_products = lookup["global_by_sku"].get(sku, [])
        if len(orderpro_products) == 1:
            warning = "SKU matches legacy products too; using the single current OrderPro product." if len(global_products) > 1 else None
            return orderpro_products[0], "sku", warning
        if len(orderpro_products) > 1:
            return None, None, "SKU matches multiple current OrderPro products."
        if global_products:
            return None, "legacy_only_sku", "SKU only matches legacy products; not auto-matching."
    barcode = normalize_code(row["barcode"])
    if barcode:
        orderpro_matches = lookup["orderpro_unique_barcodes"].get(barcode)
        global_products = lookup["global_barcode_groups"].get(barcode, [])
        if orderpro_matches:
            warning = "Barcode matches legacy products too; using the single current OrderPro product." if len(global_products) > 1 else None
            return orderpro_matches, "unique_barcode", warning
        if barcode in lookup["orderpro_duplicate_barcodes"]:
            return None, None, "Barcode matches multiple current OrderPro products."
        if global_products:
            return None, "legacy_only_barcode", "Barcode only matches legacy products; not auto-matching."
    return None, None, None


def _unique_products_from_sku_entries(entries: list[dict[str, Any]]) -> list[Product]:
    by_id: dict[int, Product] = {}
    for entry in entries:
        product = entry["product"]
        by_id[product.id] = product
    return list(by_id.values())


def _product_match_diagnostic(
    row: dict[str, str | None],
    lookup: dict[str, Any],
    method: str | None,
) -> str | None:
    sku = normalize_code(row["sku"])
    if method == "sku" and sku and len(lookup["global_by_sku"].get(sku, [])) > 1:
        return "sku_global_duplicate_but_single_orderpro_match"
    if method == "legacy_only_sku":
        return "legacy_only_product_match"
    barcode = normalize_code(row["barcode"])
    if method == "unique_barcode" and barcode and len(lookup["global_barcode_groups"].get(barcode, [])) > 1:
        return "barcode_global_duplicate_but_single_orderpro_match"
    if method == "legacy_only_barcode":
        return "legacy_only_product_match"
    return None


def _product_sku_matched_field(
    row: dict[str, str | None],
    lookup: dict[str, Any],
    product: Product | None,
) -> str | None:
    if product is None:
        return None
    sku = normalize_code(row["sku"])
    if not sku:
        return None
    for entry in lookup["orderpro_by_sku"].get(sku, []):
        if entry["product"].id == product.id:
            return entry["field"]
    return None


def _match_supplier(row: dict[str, str | None], lookup: dict[str, Any]) -> tuple[Supplier | None, str | None, str | None]:
    code = normalize_code(row["supplier_code"])
    if code and code in lookup["by_code"]:
        return lookup["by_code"][code], "supplier_code", None
    if row["supplier_orderpro_id"]:
        supplier = lookup["by_orderpro_id"].get(str(row["supplier_orderpro_id"]))
        if supplier:
            return supplier, "supplier_orderpro_id", None
        code_from_id = normalize_code(row["supplier_orderpro_id"])
        if code_from_id and code_from_id in lookup["by_code"]:
            return lookup["by_code"][code_from_id], "supplier_code", None
    name = normalize_name(row["supplier_name"])
    if name:
        if name in lookup["unique_names"]:
            return lookup["unique_names"][name], "unique_name", None
        if name in lookup["duplicate_names"]:
            return None, None, "Supplier name matches multiple local suppliers."
    return None, None, None


def _summarize_rows(
    db: Session,
    rows: list[dict[str, Any]],
    header_diagnostics: dict[str, Any] | None = None,
    product_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    product_methods = Counter(row["product_match_method"] for row in rows if row["product_match_method"])
    supplier_methods = Counter(row["supplier_match_method"] for row in rows if row["supplier_match_method"])
    diagnostics = Counter(row["product_match_diagnostic"] for row in rows if row.get("product_match_diagnostic"))
    sku_field_counts = Counter(row["product_sku_matched_field"] for row in rows if row.get("product_sku_matched_field"))
    invalid_reasons = Counter(reason for row in rows for reason in _invalid_reasons(row))
    classes = Counter(row["classification"] for row in rows)
    existing_reviews = {
        review.product_id
        for review in db.query(ProductSupplierAssignmentReview)
        .filter(ProductSupplierAssignmentReview.product_id.in_([row["product_id"] for row in rows if row["product_id"]]) if rows else False)
        .all()
    }
    suggestion_rows = [row for row in rows if row["classification"] in {"suggestion", "confirm_candidate"}]
    missing_after = (
        db.query(Product)
        .filter(
            Product.supplier_id.is_(None),
            (Product.source_system == "orderpro") | (Product.orderpro_id.is_not(None)) | (Product.orderpro_sku.is_not(None)),
        )
        .count()
        - len([row for row in rows if row["can_confirm_exact_code"]])
    )
    return {
        "rows_read": len(rows),
        "rows_valid": sum(1 for row in rows if row["valid"]),
        "rows_invalid": sum(1 for row in rows if not row["valid"]),
        "products_matched_by_orderpro_id": product_methods.get("orderpro_id", 0),
        "products_matched_by_sku": product_methods.get("sku", 0),
        "products_matched_by_unique_barcode": product_methods.get("unique_barcode", 0),
        "products_not_matched": sum(1 for row in rows if row["valid"] and not row["product_id"]),
        "sku_global_duplicate_but_single_orderpro_match": diagnostics.get("sku_global_duplicate_but_single_orderpro_match", 0),
        "barcode_global_duplicate_but_single_orderpro_match": diagnostics.get("barcode_global_duplicate_but_single_orderpro_match", 0),
        "sku_duplicate_among_orderpro_products": (product_diagnostics or {}).get("duplicate_orderpro_sku_key_count", 0),
        "barcode_duplicate_among_orderpro_products": (product_diagnostics or {}).get("duplicate_orderpro_barcode_key_count", 0),
        "rows_with_duplicate_orderpro_sku_match": sum(
            1 for row in rows if "SKU matches multiple current OrderPro products." in row["warnings"]
        ),
        "rows_with_duplicate_orderpro_barcode_match": sum(
            1 for row in rows if "Barcode matches multiple current OrderPro products." in row["warnings"]
        ),
        "legacy_only_product_matches": diagnostics.get("legacy_only_product_match", 0),
        "blank_orderpro_product_sku_count": (product_diagnostics or {}).get("blank_orderpro_product_sku_count", 0),
        "blank_orderpro_product_barcode_count": (product_diagnostics or {}).get("blank_orderpro_product_barcode_count", 0),
        "nonblank_orderpro_sku_key_count": (product_diagnostics or {}).get("nonblank_orderpro_sku_key_count", 0),
        "nonblank_orderpro_barcode_key_count": (product_diagnostics or {}).get("nonblank_orderpro_barcode_key_count", 0),
        "duplicate_orderpro_sku_key_count": (product_diagnostics or {}).get("duplicate_orderpro_sku_key_count", 0),
        "duplicate_orderpro_barcode_key_count": (product_diagnostics or {}).get("duplicate_orderpro_barcode_key_count", 0),
        "duplicate_orderpro_sku_keys_sample": (product_diagnostics or {}).get("duplicate_orderpro_sku_keys_sample", []),
        "duplicate_orderpro_barcode_keys_sample": (product_diagnostics or {}).get("duplicate_orderpro_barcode_keys_sample", []),
        "export_rows_with_blank_sku": sum(1 for row in rows if not row["evidence_summary"].get("sku")),
        "export_rows_with_blank_barcode": sum(1 for row in rows if not row["evidence_summary"].get("barcode")),
        "export_sku_matched_field_counts": {
            "product_sku": sku_field_counts.get("product_sku", 0),
            "product_orderpro_sku": sku_field_counts.get("product_orderpro_sku", 0),
        },
        "export_barcode_match_count": product_methods.get("unique_barcode", 0),
        "suppliers_matched_by_code": supplier_methods.get("supplier_code", 0),
        "suppliers_matched_by_orderpro_id": supplier_methods.get("supplier_orderpro_id", 0),
        "suppliers_matched_by_unique_name": supplier_methods.get("unique_name", 0),
        "suppliers_not_matched": sum(1 for row in rows if row["valid"] and not row["supplier_id"]),
        "review_suggestions_to_create": sum(1 for row in suggestion_rows if row["product_id"] not in existing_reviews),
        "review_suggestions_to_update": sum(1 for row in suggestion_rows if row["product_id"] in existing_reviews),
        "products_that_would_be_confirmed": sum(1 for row in rows if row["can_confirm_exact_code"]),
        "products_with_existing_supplier_same": classes.get("existing_same_supplier", 0),
        "products_with_existing_supplier_conflict": classes.get("existing_supplier_conflict", 0),
        "products_still_missing_supplier_after_apply_estimate": max(missing_after, 0),
        "exact_code_confirmation_candidates": sum(1 for row in rows if row["can_confirm_exact_code"]),
        "name_only_suggestions": sum(1 for row in rows if row["supplier_match_method"] == "unique_name"),
        "conflicts": classes.get("existing_supplier_conflict", 0),
        "classification_counts": dict(classes),
        "warnings": sorted({warning for row in rows for warning in row["warnings"]}),
        "detected_columns": (header_diagnostics or {}).get("detected_columns", []),
        "mapped_columns": (header_diagnostics or {}).get("mapped_columns", {}),
        "missing_optional_columns": (header_diagnostics or {}).get("missing_optional_columns", []),
        "missing_required_columns": (header_diagnostics or {}).get("missing_required_columns", []),
        "invalid_row_reason_counts": dict(invalid_reasons),
        "sample_orderpro_sku_matches": [row for row in rows if row["product_match_method"] == "sku"][:10],
        "sample_orderpro_barcode_matches": [row for row in rows if row["product_match_method"] == "unique_barcode"][:10],
        "sample_duplicate_orderpro_sku_keys": (product_diagnostics or {}).get("duplicate_orderpro_sku_keys_sample", []),
        "sample_legacy_only_matches": [
            row for row in rows if row.get("product_match_diagnostic") == "legacy_only_product_match"
        ][:10],
        "sample_confirm_candidates": [row for row in rows if row["can_confirm_exact_code"]][:10],
        "sample_suggestions": suggestion_rows[:10],
        "sample_unmatched_products": [row for row in rows if row["valid"] and not row["product_id"]][:10],
        "sample_unmatched_suppliers": [row for row in rows if row["valid"] and not row["supplier_id"]][:10],
    }


def _invalid_reasons(row: dict[str, Any]) -> list[str]:
    evidence = row.get("evidence_summary") or {}
    reasons = []
    if row["valid"]:
        return reasons
    if not (evidence.get("orderpro_product_id") or evidence.get("sku") or evidence.get("barcode")):
        reasons.append("missing_product_identity")
    if not (evidence.get("supplier_code") or evidence.get("supplier_orderpro_id") or evidence.get("supplier_name")):
        reasons.append("missing_supplier_identity")
    return reasons


def _header_diagnostics(rows: list[dict[str, str | None]]) -> dict[str, Any]:
    detected = sorted({column for row in rows for column in row})
    groups = {
        "product_id": PRODUCT_ID_COLUMNS,
        "sku": SKU_COLUMNS,
        "barcode": BARCODE_COLUMNS,
        "product_name": NAME_COLUMNS,
        "supplier_code": SUPPLIER_CODE_COLUMNS,
        "supplier_orderpro_id": SUPPLIER_ID_COLUMNS,
        "supplier_name": SUPPLIER_NAME_COLUMNS,
        "supplier_sku": SUPPLIER_SKU_COLUMNS,
        "lead_time_days": LEAD_TIME_COLUMNS,
        "cost_price": COST_PRICE_COLUMNS,
        "min_order_qty": MOQ_COLUMNS,
    }
    mapped = {
        canonical: sorted(set(detected).intersection(names))
        for canonical, names in groups.items()
        if set(detected).intersection(names)
    }
    has_product_identity = any(key in mapped for key in ("product_id", "sku", "barcode"))
    has_supplier_identity = any(key in mapped for key in ("supplier_code", "supplier_orderpro_id", "supplier_name"))
    optional = sorted(set(groups) - set(mapped))
    missing_required = []
    if not has_product_identity:
        missing_required.append("product_identity")
    if not has_supplier_identity:
        missing_required.append("supplier_identity")
    return {
        "detected_columns": detected,
        "mapped_columns": mapped,
        "missing_optional_columns": optional,
        "missing_required_columns": missing_required,
    }


def positive_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def positive_int(value: Any, *, maximum: int | None = None) -> int | None:
    parsed = positive_float(value)
    if parsed is None:
        return None
    rounded = int(round(parsed))
    if rounded <= 0 or (maximum is not None and rounded > maximum):
        return None
    return rounded
