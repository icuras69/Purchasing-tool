from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_
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


class ManualSupplierCleanupConflict(ValueError):
    pass


REVIEW_STATUSES = {"deferred", "rejected", "needs_information"}


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


def list_cleanup_candidates(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    priority_only: bool = False,
    sort_by: str = "priority",
    sort_direction: str = "desc",
    has_open_demand: bool | None = None,
    has_stock: bool | None = None,
    has_demand_history: bool | None = None,
    has_cost: bool | None = None,
    has_existing_suggestion: bool | None = None,
) -> dict[str, Any]:
    rows = [_cleanup_row_for_product(db, product) for product in missing_supplier_products(db)]
    summary = _candidate_summary(rows)
    rows = _filter_candidate_rows(
        rows,
        search=search,
        priority_only=priority_only,
        has_open_demand=has_open_demand,
        has_stock=has_stock,
        has_demand_history=has_demand_history,
        has_cost=has_cost,
        has_existing_suggestion=has_existing_suggestion,
    )
    rows = _sort_candidate_rows(rows, sort_by=sort_by, sort_direction=sort_direction)
    total = len(rows)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 250)
    start = (page - 1) * page_size
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": rows[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "summary": summary,
    }


def get_cleanup_candidate(db: Session, product_id: int) -> dict[str, Any] | None:
    product = db.get(Product, product_id)
    if product is None:
        return None
    if product.supplier_id is not None:
        return None
    return _cleanup_detail_for_product(db, product)


def search_cleanup_suppliers(
    db: Session,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    query = db.query(Supplier).filter(Supplier.is_active.is_(True))
    normalized = _normalize_text(search)
    if normalized:
        like = f"%{normalized.lower()}%"
        query = query.filter(
            or_(
                func.lower(Supplier.name).like(like),
                func.lower(Supplier.orderpro_code).like(like),
            )
        )
    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    suppliers = (
        query.order_by(Supplier.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    product_counts = dict(
        db.query(Product.supplier_id, func.count(Product.id))
        .filter(Product.supplier_id.in_([supplier.id for supplier in suppliers] or [-1]))
        .group_by(Product.supplier_id)
        .all()
    )
    return {
        "items": [
            {
                "id": supplier.id,
                "name": supplier.name,
                "orderpro_id": supplier.orderpro_id,
                "orderpro_code": supplier.orderpro_code,
                "is_active": supplier.is_active,
                "lead_time_days": supplier.lead_time_days,
                "assigned_product_count": int(product_counts.get(supplier.id, 0)),
            }
            for supplier in suppliers
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


def assign_supplier_to_product(
    db: Session,
    *,
    product_id: int,
    supplier_id: int,
    reviewed_by: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Product not found.")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError("Supplier not found.")
    if product.supplier_id is not None and product.supplier_id != supplier.id:
        raise ManualSupplierCleanupConflict("Product already has a different supplier assignment.")
    review = _confirm_product_supplier(
        db,
        product=product,
        supplier=supplier,
        reviewed_by=reviewed_by,
        notes=notes,
        evidence_source="manual_supplier_cleanup",
        evidence_extra={"source": "manual_supplier_cleanup", "assignment_method": "local_supplier_id"},
    )
    db.commit()
    db.refresh(product)
    db.refresh(review)
    return {
        "product": _cleanup_detail_for_product(db, product, include_assigned=True),
        "review": _serialize_review(review),
    }


def record_cleanup_review(
    db: Session,
    *,
    product_id: int,
    status: str,
    reviewed_by: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"Unsupported review status: {status}.")
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Product not found.")
    now = datetime.utcnow()
    review = product.supplier_assignment_review
    if review is None:
        review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
        db.add(review)
    suggestion = review_item_for_product(db, product)
    review.suggested_supplier_id = suggestion.get("suggested_supplier_id")
    review.suggestion_source = suggestion.get("suggestion_source")
    review.confidence_label = suggestion.get("existing_confidence_label") or suggestion.get("confidence_label") or "none"
    review.confidence_score = float(suggestion.get("confidence_score") or 0.0)
    review.status = status
    review.reviewed_by = reviewed_by
    review.reviewed_at = now
    review.notes = notes
    review.evidence_summary = {
        "source": "manual_supplier_cleanup",
        "review_status": status,
        "previous_evidence": suggestion.get("evidence_summary") or {},
    }
    review.warnings = suggestion.get("warnings") or []
    review.updated_at = now
    db.commit()
    db.refresh(review)
    return {"review": _serialize_review(review)}


def get_cleanup_summary(db: Session) -> dict[str, Any]:
    total_products = (
        db.query(Product)
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None)),
        )
        .count()
    )
    products_with_supplier = (
        db.query(Product)
        .filter(Product.supplier_id.is_not(None))
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None)),
        )
        .count()
    )
    candidate_page = list_cleanup_candidates(db, page=1, page_size=1)
    status_counts = dict(
        db.query(ProductSupplierAssignmentReview.status, func.count(ProductSupplierAssignmentReview.id))
        .group_by(ProductSupplierAssignmentReview.status)
        .all()
    )
    completion = (products_with_supplier / total_products * 100) if total_products else 0
    return {
        "total_products": total_products,
        "products_with_supplier": products_with_supplier,
        "products_missing_supplier": candidate_page["summary"]["total_missing_supplier"],
        "priority_missing_supplier_products": candidate_page["summary"]["priority_candidates"],
        "confirmed_manual_assignments": status_counts.get("confirmed", 0),
        "deferred_reviews": status_counts.get("deferred", 0),
        "rejected_reviews": status_counts.get("rejected", 0),
        "needs_information_reviews": status_counts.get("needs_information", 0),
        "completion_percentage": round(completion, 2),
    }


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
        _confirm_product_supplier(
            db,
            product=product,
            supplier=supplier,
            reviewed_by=reviewed_by,
            notes=row["review_note"],
            now=now,
            evidence_source="manual_supplier_cleanup",
            evidence_extra={
                "source": "manual_supplier_cleanup",
                "row_number": row["row_number"],
                "supplier_match_method": row["supplier_match_method"],
                "reviewed_supplier_id": row["reviewed_supplier_id"],
                "reviewed_supplier_code": row["reviewed_supplier_code"],
                "reviewed_supplier_name": row["reviewed_supplier_name"],
                "review_note": row["review_note"],
            },
            warnings=row["warnings"],
        )
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


def _cleanup_detail_for_product(db: Session, product: Product, *, include_assigned: bool = False) -> dict[str, Any]:
    row = _cleanup_row_for_product(db, product) if product.supplier_id is None else {
        "product_id": product.id,
        "orderpro_id": product.orderpro_id,
        "orderpro_sku": product.orderpro_sku,
        "product_name": product.name,
        "barcode": product.barcode,
        "brand": product.brand,
        "category": product.category,
        "current_stock": float(product.current_stock or 0),
        "demand_history_available": False,
        "open_customer_demand": 0,
        "seasonality_tag": product.seasonality_tag,
        "cost_price": product.cost_price,
        "cost_source": "product" if product.cost_price is not None else None,
        "lead_time_status": "available" if product.lead_time_days else "missing",
        "forecast_readiness_score": None,
        "blocking_issues": [],
        "warning_issues": [],
        "existing_suggested_supplier_id": None,
        "existing_suggested_supplier_name": None,
        "existing_suggestion_source": None,
        "existing_confidence_label": "none",
        "evidence_summary": {},
        "review_status": product.supplier_assignment_review.status if product.supplier_assignment_review else "confirmed",
        "priority_score": 0,
        "priority_reason": "",
        "suggested_action": "assigned",
    }
    review = product.supplier_assignment_review
    row.update(
        {
            "description": product.description,
            "supplier_id": product.supplier_id if include_assigned else None,
            "supplier_name": product.supplier_record.name if product.supplier_record else None,
            "supplier_code": product.supplier_record.orderpro_code if product.supplier_record else None,
            "review": _serialize_review(review) if review else None,
        }
    )
    return row


def _filter_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    search: str | None = None,
    priority_only: bool = False,
    has_open_demand: bool | None = None,
    has_stock: bool | None = None,
    has_demand_history: bool | None = None,
    has_cost: bool | None = None,
    has_existing_suggestion: bool | None = None,
) -> list[dict[str, Any]]:
    filtered = rows
    needle = _normalize_name(search)
    if needle:
        filtered = [
            row
            for row in filtered
            if needle in " ".join(
                str(row.get(field) or "").lower()
                for field in ("orderpro_sku", "product_name", "barcode", "description")
            )
        ]
    if priority_only:
        filtered = [row for row in filtered if row["priority_score"] > 0]
    if has_open_demand is not None:
        filtered = [row for row in filtered if (row["open_customer_demand"] > 0) is has_open_demand]
    if has_stock is not None:
        filtered = [row for row in filtered if (row["current_stock"] > 0) is has_stock]
    if has_demand_history is not None:
        filtered = [row for row in filtered if row["demand_history_available"] is has_demand_history]
    if has_cost is not None:
        filtered = [row for row in filtered if (row["cost_price"] is not None) is has_cost]
    if has_existing_suggestion is not None:
        filtered = [row for row in filtered if bool(row["existing_suggested_supplier_id"]) is has_existing_suggestion]
    return filtered


def _sort_candidate_rows(rows: list[dict[str, Any]], *, sort_by: str, sort_direction: str) -> list[dict[str, Any]]:
    reverse = sort_direction.lower() != "asc"
    key_map = {
        "priority": lambda row: (row["priority_score"], row["open_customer_demand"], -row["product_id"]),
        "sku": lambda row: (row["orderpro_sku"] or "",),
        "product_name": lambda row: (row["product_name"] or "",),
        "stock": lambda row: (row["current_stock"],),
        "open_demand": lambda row: (row["open_customer_demand"],),
    }
    key_func = key_map.get(sort_by, key_map["priority"])
    return sorted(rows, key=key_func, reverse=reverse)


def _candidate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_missing_supplier": len(rows),
        "priority_candidates": sum(1 for row in rows if row["priority_score"] > 0),
        "with_open_demand": sum(1 for row in rows if row["open_customer_demand"] > 0),
        "with_stock": sum(1 for row in rows if row["current_stock"] > 0),
        "with_demand_history": sum(1 for row in rows if row["demand_history_available"]),
        "with_cost": sum(1 for row in rows if row["cost_price"] is not None),
    }


def _confirm_product_supplier(
    db: Session,
    *,
    product: Product,
    supplier: Supplier,
    reviewed_by: str | None,
    notes: str | None,
    evidence_source: str,
    evidence_extra: dict[str, Any],
    now: datetime | None = None,
    warnings: list[str] | None = None,
) -> ProductSupplierAssignmentReview:
    now = now or datetime.utcnow()
    review = product.supplier_assignment_review
    if review is None:
        review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
        db.add(review)
    product.supplier_id = supplier.id
    review.suggested_supplier_id = supplier.id
    review.suggestion_source = evidence_source
    review.confidence_label = "manual"
    review.confidence_score = 1.0
    review.status = "confirmed"
    review.reviewed_supplier_id = supplier.id
    review.reviewed_by = reviewed_by
    review.reviewed_at = now
    review.notes = notes
    review.evidence_summary = evidence_extra
    review.warnings = warnings or []
    review.updated_at = now
    return review


def _serialize_review(review: ProductSupplierAssignmentReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "product_id": review.product_id,
        "suggested_supplier_id": review.suggested_supplier_id,
        "suggestion_source": review.suggestion_source,
        "confidence_label": review.confidence_label,
        "confidence_score": review.confidence_score,
        "status": review.status,
        "evidence_summary": review.evidence_summary,
        "warnings": review.warnings or [],
        "reviewed_supplier_id": review.reviewed_supplier_id,
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "notes": review.notes,
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
