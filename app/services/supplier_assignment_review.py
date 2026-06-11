from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.forecasting import build_forecast


REVIEW_STATUSES = {"needs_review", "suggested", "confirmed", "rejected", "no_evidence"}
STRICT_AUTO_CONFIRM_SOURCES = {"supplier_code_csv", "orderpro_purchase_orders_repeated"}


@dataclass
class SupplierAssignmentPlan:
    mode: str
    summary: dict[str, Any]
    items: list[dict[str, Any]]
    records_created: int = 0
    records_updated: int = 0
    products_confirmed: int = 0


def is_orderpro_product(product: Product) -> bool:
    return bool(
        product.source_system == "orderpro"
        or product.orderpro_id is not None
        or product.orderpro_sku is not None
    )


def missing_supplier_products(db: Session, *, product_id: int | None = None) -> list[Product]:
    query = (
        db.query(Product)
        .options(
            selectinload(Product.supplier_assignment_review),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.seasonality_profile),
        )
        .filter(Product.supplier_id.is_(None))
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
    )
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    return query.order_by(Product.id.asc()).all()


def review_item_for_product(db: Session, product: Product) -> dict[str, Any]:
    suggestion = suggest_supplier_for_product(db, product)
    review = product.supplier_assignment_review
    forecast = _safe_forecast(db, product)
    demand_history_available = _has_demand_history(forecast)
    open_customer_demand = float(forecast.get("total_open_demand") or 0)
    status = review.status if review else suggestion["status"]

    return {
        "product_id": product.id,
        "orderpro_id": product.orderpro_id,
        "orderpro_sku": product.orderpro_sku,
        "name": product.name,
        "barcode": product.barcode,
        "brand": product.brand,
        "category": product.category,
        "current_stock": product.current_stock,
        "demand_history_available": demand_history_available,
        "open_customer_demand": open_customer_demand,
        "seasonality_tag": product.seasonality_tag,
        "cost_source": forecast.get("cost_source"),
        "lead_time_status": "available" if forecast.get("lead_time_days_used") else "missing",
        "suggested_supplier_id": suggestion["suggested_supplier_id"],
        "suggested_supplier_name": suggestion["suggested_supplier_name"],
        "suggestion_source": suggestion["suggestion_source"],
        "confidence_label": suggestion["confidence_label"],
        "confidence_score": suggestion["confidence_score"],
        "evidence_summary": suggestion["evidence_summary"],
        "evidence_date": suggestion["evidence_date"],
        "warnings": suggestion["warnings"],
        "status": status,
        "review_id": review.id if review else None,
        "reviewed_supplier_id": review.reviewed_supplier_id if review else None,
        "reviewed_by": review.reviewed_by if review else None,
        "reviewed_at": review.reviewed_at.isoformat() if review and review.reviewed_at else None,
    }


def suggest_supplier_for_product(db: Session, product: Product) -> dict[str, Any]:
    if product.supplier_id is not None:
        supplier = product.supplier_record or db.get(Supplier, product.supplier_id)
        return _suggestion(
            supplier=supplier,
            source="already_assigned",
            confidence_label="high",
            confidence_score=1.0,
            status="confirmed",
            evidence={"message": "Product already has a local supplier assignment."},
        )

    orderpro_evidence = _orderpro_po_evidence(db, product.id)
    if orderpro_evidence:
        return orderpro_evidence

    local_evidence = _local_po_evidence(db, product.id)
    if local_evidence:
        return local_evidence

    legacy_evidence = _legacy_product_supplier_evidence(product)
    if legacy_evidence:
        return legacy_evidence

    return _suggestion(
        supplier=None,
        source="none",
        confidence_label="none",
        confidence_score=0.0,
        status="no_evidence",
        evidence={"message": "No deterministic supplier evidence is available locally."},
    )


def _orderpro_po_evidence(db: Session, product_id: int) -> dict[str, Any] | None:
    rows = (
        db.query(OrderProPurchaseOrderLine, OrderProPurchaseOrder)
        .join(OrderProPurchaseOrder, OrderProPurchaseOrderLine.orderpro_purchase_order_id == OrderProPurchaseOrder.id)
        .filter(OrderProPurchaseOrderLine.product_id == product_id)
        .filter(OrderProPurchaseOrder.supplier_id.is_not(None))
        .order_by(
            OrderProPurchaseOrder.order_date.desc().nullslast(),
            OrderProPurchaseOrder.updated_at.desc(),
            OrderProPurchaseOrder.id.desc(),
        )
        .all()
    )
    return _evidence_from_po_rows(rows, source_prefix="orderpro_purchase_order")


def _local_po_evidence(db: Session, product_id: int) -> dict[str, Any] | None:
    rows = (
        db.query(PurchaseOrderLine, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .filter(PurchaseOrderLine.product_id == product_id)
        .filter(PurchaseOrder.supplier_id.is_not(None))
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        .all()
    )
    return _evidence_from_po_rows(rows, source_prefix="local_purchase_order")


def _evidence_from_po_rows(rows: list[tuple[Any, Any]], *, source_prefix: str) -> dict[str, Any] | None:
    if not rows:
        return None

    grouped: dict[int, list[tuple[Any, Any]]] = defaultdict(list)
    for line, po in rows:
        grouped[po.supplier_id].append((line, po))

    latest_line, latest_po = rows[0]
    supplier = latest_po.supplier
    supplier_count = len(grouped)
    warnings = []
    if supplier_count > 1:
        warnings.append("Conflicting supplier evidence exists across purchase orders.")
        confidence_label = "low"
        confidence_score = 0.35
        source = f"{source_prefix}_conflicting"
    elif len(rows) >= 2:
        confidence_label = "high"
        confidence_score = 0.9
        source = f"{source_prefix}s_repeated"
    else:
        confidence_label = "medium"
        confidence_score = 0.65
        source = f"{source_prefix}_line"

    evidence_date = _po_evidence_date(latest_po)
    evidence = {
        "source": source,
        "purchase_order_id": latest_po.id,
        "purchase_order_number": getattr(latest_po, "purchase_order_number", None),
        "line_id": latest_line.id,
        "supplier_id": latest_po.supplier_id,
        "supplier_name": supplier.name if supplier else getattr(latest_po, "supplier_name", None),
        "evidence_count": len(rows),
        "supplier_evidence_counts": {str(key): len(value) for key, value in grouped.items()},
        "latest_status": getattr(latest_po, "status", None),
        "latest_date": evidence_date,
    }
    return _suggestion(
        supplier=supplier,
        source=source,
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        status="suggested",
        evidence=evidence,
        evidence_date=evidence_date,
        warnings=warnings,
    )


def _legacy_product_supplier_evidence(product: Product) -> dict[str, Any] | None:
    mappings = [
        mapping
        for mapping in product.product_suppliers
        if mapping.supplier_id is not None and mapping.match_status != "rejected"
    ]
    if not mappings:
        return None
    preferred = next((mapping for mapping in mappings if mapping.is_preferred), None)
    mapping = preferred or mappings[0]
    supplier = mapping.supplier
    evidence = {
        "source": "legacy_product_supplier",
        "mapping_id": mapping.id,
        "match_status": mapping.match_status,
        "match_method": mapping.match_method,
        "supplier_sku": mapping.supplier_sku,
    }
    return _suggestion(
        supplier=supplier,
        source="legacy_product_supplier",
        confidence_label="low",
        confidence_score=0.35,
        status="suggested",
        evidence=evidence,
        evidence_date=mapping.updated_at.isoformat() if mapping.updated_at else None,
        warnings=["Legacy ProductSupplier mappings are transitional evidence only."],
    )


def _po_evidence_date(po: Any) -> str | None:
    for field in ("order_date", "expected_date", "updated_at", "created_at"):
        value = getattr(po, field, None)
        if isinstance(value, datetime):
            return value.isoformat()
    return None


def _suggestion(
    *,
    supplier: Supplier | None,
    source: str,
    confidence_label: str,
    confidence_score: float,
    status: str,
    evidence: dict[str, Any],
    evidence_date: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "suggested_supplier_id": supplier.id if supplier else None,
        "suggested_supplier_name": supplier.name if supplier else None,
        "suggestion_source": source,
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "status": status,
        "evidence_summary": evidence,
        "evidence_date": evidence_date,
        "warnings": warnings or [],
    }


def build_supplier_assignment_review_report(
    db: Session,
    *,
    product_id: int | None = None,
    supplier_id: int | None = None,
) -> SupplierAssignmentPlan:
    products = missing_supplier_products(db, product_id=product_id)
    items = [review_item_for_product(db, product) for product in products]
    if supplier_id is not None:
        items = [item for item in items if item["suggested_supplier_id"] == supplier_id]
    return SupplierAssignmentPlan(
        mode="dry-run",
        summary=summarize_review_items(db, items),
        items=items,
    )


def summarize_review_items(db: Session, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if items is None:
        items = build_supplier_assignment_review_report(db).items
    total_orderpro = (
        db.query(Product)
        .filter(
            (Product.source_system == "orderpro")
            | (Product.orderpro_id.is_not(None))
            | (Product.orderpro_sku.is_not(None))
        )
        .count()
    )
    confidence_counts = Counter(item["confidence_label"] for item in items)
    source_counts = Counter(item["suggestion_source"] for item in items)
    status_counts = Counter(item["status"] for item in items)
    brand_counts = Counter(item["brand"] or "Unknown" for item in items)
    category_counts = Counter(item["category"] or "Unknown" for item in items)
    return {
        "total_orderpro_products": total_orderpro,
        "missing_supplier_products": len(items),
        "missing_supplier_products_with_stock": sum(1 for item in items if (item["current_stock"] or 0) > 0),
        "missing_supplier_products_with_demand_history": sum(1 for item in items if item["demand_history_available"]),
        "missing_supplier_products_with_open_customer_demand": sum(
            1 for item in items if item["open_customer_demand"] > 0
        ),
        "missing_supplier_products_with_seasonality_profile": sum(
            1 for item in items if item["seasonality_tag"] not in {None, "insufficient_data"}
        ),
        "missing_supplier_products_with_po_supplier_evidence": sum(
            1
            for item in items
            if item["suggestion_source"] in {
                "orderpro_purchase_order_line",
                "orderpro_purchase_orders_repeated",
                "orderpro_purchase_order_conflicting",
                "local_purchase_order_line",
                "local_purchase_orders_repeated",
                "local_purchase_order_conflicting",
            }
        ),
        "missing_supplier_products_with_no_evidence": sum(
            1 for item in items if item["confidence_label"] == "none"
        ),
        "suggested_supplier_count_by_confidence": dict(confidence_counts),
        "suggestion_count_by_source": dict(source_counts),
        "review_status_counts": dict(status_counts),
        "no_suggestion_count": sum(1 for item in items if item["suggested_supplier_id"] is None),
        "top_categories_affected": dict(category_counts.most_common(10)),
        "top_brands_affected": dict(brand_counts.most_common(10)),
    }


def filter_review_items(
    items: list[dict[str, Any]],
    *,
    status: str | None = None,
    confidence: str | None = None,
    suggestion_source: str | None = None,
    has_stock: bool | None = None,
    has_demand: bool | None = None,
    has_open_demand: bool | None = None,
    category: str | None = None,
    brand: str | None = None,
    supplier_id: int | None = None,
) -> list[dict[str, Any]]:
    filtered = items
    if status:
        filtered = [item for item in filtered if item["status"] == status]
    if confidence:
        filtered = [item for item in filtered if item["confidence_label"] == confidence]
    if suggestion_source:
        filtered = [item for item in filtered if item["suggestion_source"] == suggestion_source]
    if has_stock is not None:
        filtered = [item for item in filtered if ((item["current_stock"] or 0) > 0) is has_stock]
    if has_demand is not None:
        filtered = [item for item in filtered if item["demand_history_available"] is has_demand]
    if has_open_demand is not None:
        filtered = [item for item in filtered if (item["open_customer_demand"] > 0) is has_open_demand]
    if category:
        filtered = [item for item in filtered if item["category"] == category]
    if brand:
        filtered = [item for item in filtered if item["brand"] == brand]
    if supplier_id is not None:
        filtered = [item for item in filtered if item["suggested_supplier_id"] == supplier_id]
    return filtered


def apply_supplier_assignment_suggestions(
    db: Session,
    *,
    product_id: int | None = None,
    supplier_id: int | None = None,
    confirm_high_confidence: bool = False,
    reviewed_by: str | None = None,
) -> SupplierAssignmentPlan:
    plan = build_supplier_assignment_review_report(db, product_id=product_id, supplier_id=supplier_id)
    created = 0
    updated = 0
    confirmed = 0
    now = datetime.utcnow()
    for item in plan.items:
        product = db.get(Product, item["product_id"])
        if product is None:
            continue
        review = product.supplier_assignment_review
        if review is None:
            review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
            db.add(review)
            created += 1
        else:
            updated += 1
        _apply_item_to_review(review, item, now)
        if (
            confirm_high_confidence
            and item["suggested_supplier_id"] is not None
            and item["confidence_label"] == "high"
            and item["suggestion_source"] in STRICT_AUTO_CONFIRM_SOURCES
        ):
            product.supplier_id = item["suggested_supplier_id"]
            review.status = "confirmed"
            review.reviewed_supplier_id = item["suggested_supplier_id"]
            review.reviewed_by = reviewed_by or "supplier-assignment-review"
            review.reviewed_at = now
            confirmed += 1
    db.commit()
    plan.mode = "apply"
    plan.records_created = created
    plan.records_updated = updated
    plan.products_confirmed = confirmed
    return plan


def confirm_supplier_assignment(
    db: Session,
    *,
    product_id: int,
    supplier_id: int,
    reviewed_by: str | None = None,
    note: str | None = None,
) -> ProductSupplierAssignmentReview:
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Product not found.")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError("Supplier not found.")
    now = datetime.utcnow()
    review = product.supplier_assignment_review
    if review is None:
        review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
        db.add(review)
    suggestion = suggest_supplier_for_product(db, product)
    _apply_item_to_review(review, {**suggestion, "product_id": product.id}, now)
    product.supplier_id = supplier.id
    review.status = "confirmed"
    review.reviewed_supplier_id = supplier.id
    review.reviewed_by = reviewed_by
    review.reviewed_at = now
    review.notes = note
    review.updated_at = now
    db.commit()
    db.refresh(review)
    return review


def reject_supplier_assignment(
    db: Session,
    *,
    product_id: int,
    reason: str | None = None,
    reviewed_by: str | None = None,
) -> ProductSupplierAssignmentReview:
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError("Product not found.")
    now = datetime.utcnow()
    review = product.supplier_assignment_review
    if review is None:
        review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
        db.add(review)
    suggestion = suggest_supplier_for_product(db, product)
    _apply_item_to_review(review, {**suggestion, "product_id": product.id}, now)
    review.status = "rejected"
    review.reviewed_by = reviewed_by
    review.reviewed_at = now
    review.notes = reason
    review.updated_at = now
    db.commit()
    db.refresh(review)
    return review


def _apply_item_to_review(
    review: ProductSupplierAssignmentReview,
    item: dict[str, Any],
    now: datetime,
) -> None:
    review.suggested_supplier_id = item.get("suggested_supplier_id")
    review.suggestion_source = item.get("suggestion_source")
    review.confidence_label = item.get("confidence_label") or "none"
    review.confidence_score = float(item.get("confidence_score") or 0.0)
    review.status = item.get("status") or "needs_review"
    review.evidence_summary = item.get("evidence_summary")
    review.warnings = item.get("warnings") or []
    review.updated_at = now


def _safe_forecast(db: Session, product: Product) -> dict[str, Any]:
    try:
        return build_forecast(db, product)
    except Exception:
        return {}


def _has_demand_history(forecast: dict[str, Any]) -> bool:
    return bool(
        (forecast.get("shipped_units_in_window") or 0) > 0
        or (forecast.get("units_sold_in_window") or 0) > 0
    )
