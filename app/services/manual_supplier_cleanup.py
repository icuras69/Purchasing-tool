from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier
from app.services.seasonality_backtesting import audit_product_forecast_inputs
from app.services.supplier_assignment_review import missing_supplier_products, review_item_for_product


CLEANUP_COLUMNS = [
    "product_id",
    "orderpro_id",
    "orderpro_sku",
    "product_name",
    "barcode",
    "brand",
    "category",
    "current_stock",
    "demand_history_available",
    "open_customer_demand",
    "seasonality_tag",
    "cost_price",
    "cost_source",
    "lead_time_status",
    "forecast_readiness_score",
    "blocking_issues",
    "warning_issues",
    "existing_suggested_supplier_id",
    "existing_suggested_supplier_name",
    "existing_suggestion_source",
    "existing_confidence_label",
    "evidence_summary",
    "priority_score",
    "priority_reason",
    "suggested_action",
    "reviewed_supplier_code",
    "reviewed_supplier_id",
    "reviewed_supplier_name",
    "review_note",
]


@dataclass
class ManualSupplierCleanupExport:
    mode: str
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    output_path: str | None = None


@dataclass
class ManualSupplierCleanupImport:
    mode: str
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    products_confirmed: int = 0


def build_missing_supplier_cleanup_export(
    db: Session,
    *,
    only_priority: bool = False,
    include_no_evidence: bool = True,
    include_suggested: bool = True,
    status: str | None = None,
) -> ManualSupplierCleanupExport:
    rows = [_cleanup_row_for_product(db, product) for product in missing_supplier_products(db)]
    if status:
        rows = [row for row in rows if row["review_status"] == status]
    if not include_no_evidence:
        rows = [row for row in rows if row["existing_confidence_label"] != "none"]
    if not include_suggested:
        rows = [row for row in rows if not row["existing_suggested_supplier_id"]]
    if only_priority:
        rows = [row for row in rows if row["priority_score"] > 0]
    rows = sorted(rows, key=lambda row: (-row["priority_score"], row["product_name"] or ""))
    return ManualSupplierCleanupExport(mode="dry-run", summary=_export_summary(rows), rows=rows)


def write_missing_supplier_cleanup_export(
    export: ManualSupplierCleanupExport,
    path: str | Path,
    *,
    file_format: str = "csv",
) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if file_format == "xlsx":
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("XLSX export requires pandas with an Excel engine installed.") from exc
        pd.DataFrame([_serializable_export_row(row) for row in export.rows], columns=CLEANUP_COLUMNS).to_excel(
            output_path,
            index=False,
        )
    else:
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CLEANUP_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in export.rows:
                writer.writerow(_serializable_export_row(row))
    export.output_path = str(output_path)
    export.summary["output_path"] = str(output_path)
    return str(output_path)


def plan_missing_supplier_cleanup_import(
    db: Session,
    path: str | Path,
    *,
    limit: int | None = None,
) -> ManualSupplierCleanupImport:
    raw_rows = _read_cleanup_rows(path, limit=limit)
    supplier_lookup = _supplier_lookup(db)
    rows = [
        _plan_import_row(db, row, row_number=index + 1, supplier_lookup=supplier_lookup)
        for index, row in enumerate(raw_rows)
    ]
    return ManualSupplierCleanupImport(mode="dry-run", summary=_import_summary(db, rows), rows=rows)


def apply_missing_supplier_cleanup_import(
    db: Session,
    path: str | Path,
    *,
    reviewed_by: str = "manual_supplier_cleanup",
    limit: int | None = None,
) -> ManualSupplierCleanupImport:
    plan = plan_missing_supplier_cleanup_import(db, path, limit=limit)
    now = datetime.utcnow()
    confirmed = 0
    for row in plan.rows:
        if row["classification"] != "confirmable":
            continue
        product = db.get(Product, row["product_id"])
        supplier = db.get(Supplier, row["supplier_id"])
        if product is None or supplier is None or product.supplier_id is not None:
            continue
        product.supplier_id = supplier.id
        review = product.supplier_assignment_review
        if review is None:
            review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
            db.add(review)
        review.suggested_supplier_id = supplier.id
        review.suggestion_source = "manual_supplier_cleanup"
        review.confidence_label = "manual"
        review.confidence_score = 1.0
        review.status = "confirmed"
        review.reviewed_supplier_id = supplier.id
        review.reviewed_by = reviewed_by
        review.reviewed_at = now
        review.notes = row["review_note"]
        review.evidence_summary = {
            "source": "manual_supplier_cleanup",
            "row_number": row["row_number"],
            "supplier_match_method": row["supplier_match_method"],
            "reviewed_supplier_id": row["reviewed_supplier_id"],
            "reviewed_supplier_code": row["reviewed_supplier_code"],
            "reviewed_supplier_name": row["reviewed_supplier_name"],
            "review_note": row["review_note"],
        }
        review.warnings = row["warnings"]
        review.updated_at = now
        confirmed += 1
    db.commit()
    plan.mode = "apply"
    plan.products_confirmed = confirmed
    plan.summary = _import_summary(db, plan.rows)
    plan.summary["rows_confirmed"] = confirmed
    return plan


def _cleanup_row_for_product(db: Session, product: Product) -> dict[str, Any]:
    item = review_item_for_product(db, product)
    readiness = audit_product_forecast_inputs(db, product)
    priority_score, priority_reasons = _priority(product, item, readiness)
    suggested_action = _suggested_action(item, priority_score)
    return {
        "product_id": product.id,
        "orderpro_id": product.orderpro_id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "barcode": product.barcode,
        "brand": product.brand,
        "category": product.category,
        "current_stock": float(product.current_stock or 0),
        "demand_history_available": item["demand_history_available"],
        "open_customer_demand": float(item["open_customer_demand"] or 0),
        "seasonality_tag": product.seasonality_tag,
        "cost_price": readiness.get("cost_price"),
        "cost_source": readiness.get("cost_source"),
        "lead_time_status": item["lead_time_status"],
        "forecast_readiness_score": readiness.get("forecast_readiness_score"),
        "blocking_issues": readiness.get("blocking_issues") or [],
        "warning_issues": readiness.get("warning_issues") or [],
        "existing_suggested_supplier_id": item["suggested_supplier_id"],
        "existing_suggested_supplier_name": item["suggested_supplier_name"],
        "existing_suggestion_source": item["suggestion_source"],
        "existing_confidence_label": item["confidence_label"],
        "evidence_summary": item["evidence_summary"],
        "review_status": item["status"],
        "priority_score": priority_score,
        "priority_reason": "; ".join(priority_reasons),
        "suggested_action": suggested_action,
        "reviewed_supplier_code": "",
        "reviewed_supplier_id": "",
        "reviewed_supplier_name": "",
        "review_note": "",
    }


def _priority(product: Product, item: dict[str, Any], readiness: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if item["open_customer_demand"] > 0:
        score += 50
        reasons.append("open customer demand")
    if (product.current_stock or 0) > 0:
        score += 20
        reasons.append("stock on hand")
    if item["demand_history_available"]:
        score += 15
        reasons.append("demand history")
    if readiness.get("cost_price") is not None:
        score += 10
        reasons.append("cost available")
    if product.seasonality_tag and product.seasonality_tag != "insufficient_data":
        score += 10
        reasons.append("usable seasonality")
    if item["suggested_supplier_id"]:
        score += 25
        reasons.append("existing supplier suggestion")
    non_supplier_blocking = [issue for issue in readiness.get("blocking_issues", []) if issue != "missing_supplier"]
    if not non_supplier_blocking:
        score += 10
        reasons.append("otherwise forecast-ready")
    if not reasons:
        reasons.append("low operational priority")
    return score, reasons


def _suggested_action(item: dict[str, Any], priority_score: int) -> str:
    if item["suggested_supplier_id"]:
        return "confirm_existing_suggestion"
    if priority_score >= 50:
        return "review_supplier"
    if priority_score > 0:
        return "needs_business_input"
    return "ignore_until_needed"


def _export_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_missing_supplier_products": len(rows),
        "exported_rows": len(rows),
        "priority_rows": sum(1 for row in rows if row["priority_score"] > 0),
        "rows_with_open_customer_demand": sum(1 for row in rows if row["open_customer_demand"] > 0),
        "rows_with_stock": sum(1 for row in rows if row["current_stock"] > 0),
        "rows_with_demand_history": sum(1 for row in rows if row["demand_history_available"]),
        "rows_with_existing_suggestion": sum(1 for row in rows if row["existing_suggested_supplier_id"]),
        "no_evidence_rows": sum(1 for row in rows if row["existing_confidence_label"] == "none"),
        "output_path": None,
    }


def _serializable_export_row(row: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(row)
    serialized["blocking_issues"] = "; ".join(row.get("blocking_issues") or [])
    serialized["warning_issues"] = "; ".join(row.get("warning_issues") or [])
    serialized["evidence_summary"] = json.dumps(row.get("evidence_summary") or {}, default=str, sort_keys=True)
    return serialized


def _read_cleanup_rows(path: str | Path, *, limit: int | None = None) -> list[dict[str, str | None]]:
    file_path = Path(path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("XLSX import requires pandas with an Excel engine installed.") from exc
        frame = pd.read_excel(file_path, dtype=str)
        if limit is not None:
            frame = frame.head(limit)
        return [
            {_normalize_column(column): _normalize_text(value) for column, value in row.items()}
            for row in frame.to_dict(orient="records")
        ]
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            rows.append({_normalize_column(key or ""): _normalize_text(value) for key, value in row.items()})
        return rows


def _plan_import_row(
    db: Session,
    row: dict[str, str | None],
    *,
    row_number: int,
    supplier_lookup: dict[str, Any],
) -> dict[str, Any]:
    product_id = _parse_int(row.get("product_id"))
    supplier_input = bool(row.get("reviewed_supplier_id") or row.get("reviewed_supplier_code") or row.get("reviewed_supplier_name"))
    supplier, supplier_method, warning = _match_reviewed_supplier(row, supplier_lookup)
    product = db.get(Product, product_id) if product_id is not None else None
    warnings = [warning] if warning else []
    classification = "skipped_no_supplier_input"
    if product is None:
        classification = "skipped_product_not_found"
    elif not supplier_input:
        classification = "skipped_no_supplier_input"
    elif supplier is None and warning == "Supplier name is ambiguous.":
        classification = "skipped_ambiguous_supplier_name"
    elif supplier is None:
        classification = "skipped_supplier_not_found"
    elif product.supplier_id == supplier.id:
        classification = "skipped_already_has_supplier_same"
    elif product.supplier_id is not None and product.supplier_id != supplier.id:
        classification = "skipped_existing_supplier_conflict"
        warnings.append("Product already has a different supplier_id; not overwriting.")
    else:
        classification = "confirmable"
    return {
        "row_number": row_number,
        "product_id": product_id,
        "product_name": row.get("product_name"),
        "supplier_id": supplier.id if supplier else None,
        "supplier_name": supplier.name if supplier else row.get("reviewed_supplier_name"),
        "supplier_match_method": supplier_method,
        "classification": classification,
        "reviewed_supplier_id": row.get("reviewed_supplier_id"),
        "reviewed_supplier_code": row.get("reviewed_supplier_code"),
        "reviewed_supplier_name": row.get("reviewed_supplier_name"),
        "review_note": row.get("review_note"),
        "warnings": warnings,
    }


def _supplier_lookup(db: Session) -> dict[str, Any]:
    suppliers = db.query(Supplier).all()
    names: dict[str, list[Supplier]] = {}
    for supplier in suppliers:
        key = _normalize_name(supplier.name)
        if key:
            names.setdefault(key, []).append(supplier)
    return {
        "by_id": {supplier.id: supplier for supplier in suppliers},
        "by_code": {
            code: supplier
            for supplier in suppliers
            for code in {_normalize_code(supplier.orderpro_code)}
            if code
        },
        "unique_names": {key: values[0] for key, values in names.items() if len(values) == 1},
        "duplicate_names": {key for key, values in names.items() if len(values) > 1},
    }


def _match_reviewed_supplier(
    row: dict[str, str | None],
    lookup: dict[str, Any],
) -> tuple[Supplier | None, str | None, str | None]:
    supplier_id = _parse_int(row.get("reviewed_supplier_id"))
    if supplier_id is not None:
        supplier = lookup["by_id"].get(supplier_id)
        return supplier, "reviewed_supplier_id" if supplier else None, None if supplier else "Supplier id not found."
    code = _normalize_code(row.get("reviewed_supplier_code"))
    if code:
        supplier = lookup["by_code"].get(code)
        return supplier, "reviewed_supplier_code" if supplier else None, None if supplier else "Supplier code not found."
    name = _normalize_name(row.get("reviewed_supplier_name"))
    if name:
        if name in lookup["unique_names"]:
            return lookup["unique_names"][name], "reviewed_supplier_name", None
        if name in lookup["duplicate_names"]:
            return None, None, "Supplier name is ambiguous."
        return None, None, "Supplier name not found."
    return None, None, None


def _import_summary(db: Session, rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["classification"] for row in rows)
    missing_estimate = (
        db.query(Product)
        .filter(
            Product.supplier_id.is_(None),
            (Product.source_system == "orderpro") | (Product.orderpro_id.is_not(None)) | (Product.orderpro_sku.is_not(None)),
        )
        .count()
        - counts.get("confirmable", 0)
    )
    return {
        "rows_read": len(rows),
        "rows_with_reviewed_supplier": sum(
            1
            for row in rows
            if row["reviewed_supplier_id"] or row["reviewed_supplier_code"] or row["reviewed_supplier_name"]
        ),
        "rows_confirmable": counts.get("confirmable", 0),
        "rows_confirmed": 0,
        "rows_skipped_no_supplier_input": counts.get("skipped_no_supplier_input", 0),
        "rows_skipped_already_has_supplier_same": counts.get("skipped_already_has_supplier_same", 0),
        "rows_skipped_existing_supplier_conflict": counts.get("skipped_existing_supplier_conflict", 0),
        "rows_skipped_supplier_not_found": counts.get("skipped_supplier_not_found", 0),
        "rows_skipped_ambiguous_supplier_name": counts.get("skipped_ambiguous_supplier_name", 0),
        "products_remaining_missing_supplier_estimate": max(missing_estimate, 0),
        "sample_confirmed": [row for row in rows if row["classification"] == "confirmable"][:10],
        "sample_skipped": [row for row in rows if row["classification"] != "confirmable"][:10],
        "warnings": sorted({warning for row in rows for warning in row["warnings"]}),
        "classification_counts": dict(counts),
    }


def _normalize_column(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _normalize_code(value: Any) -> str | None:
    text = _normalize_text(value)
    return text.upper() if text else None


def _normalize_name(value: Any) -> str | None:
    text = _normalize_text(value)
    return " ".join(text.lower().split()) if text else None


def _parse_int(value: Any) -> int | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None
