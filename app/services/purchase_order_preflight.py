from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.recommendation import Recommendation


DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def load_purchase_order_for_preflight(db: Session, purchase_order_id: int) -> PurchaseOrder | None:
    return (
        db.query(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product),
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product_supplier),
        )
        .filter(PurchaseOrder.id == purchase_order_id)
        .first()
    )


def purchase_order_preflight(db: Session, purchase_order: PurchaseOrder) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if purchase_order.supplier_id is None or purchase_order.supplier is None:
        blockers.append("Purchase order is missing a supplier.")
    elif hasattr(purchase_order.supplier, "is_active") and not purchase_order.supplier.is_active:
        blockers.append("Purchase order supplier is inactive.")

    if not purchase_order.lines:
        blockers.append("Purchase order has no lines.")

    recommendations_by_product = {
        recommendation.product_id: recommendation
        for recommendation in db.query(Recommendation)
        .filter(Recommendation.converted_purchase_order_id == purchase_order.id)
        .all()
    }
    line_checks = [
        line_preflight_check(db, purchase_order, line, recommendations_by_product.get(line.product_id))
        for line in purchase_order.lines
    ]
    for line_check in line_checks:
        blockers.extend(line_check["blockers"])
        warnings.extend(line_check["warnings"])

    canonical_supplier_ids = {
        line_check["canonical_supplier_id"]
        for line_check in line_checks
        if line_check.get("canonical_supplier_id") is not None
    }
    if len(canonical_supplier_ids) > 1:
        blockers.append("Purchase order contains products from multiple canonical suppliers.")

    blockers = unique_preserve_order(blockers)
    warnings = unique_preserve_order(warnings)
    overall_status = "blocked" if blockers else "needs_review" if warnings else "ready"
    return {
        "purchase_order_id": purchase_order.id,
        "status": purchase_order.status,
        "supplier_id": purchase_order.supplier_id,
        "supplier_name": purchase_order.supplier.name if purchase_order.supplier else None,
        "can_submit": purchase_order.status == DRAFT and not blockers,
        "can_approve": purchase_order.status == PENDING_APPROVAL and not blockers,
        "can_issue_if_applicable": purchase_order.status == APPROVED and not blockers,
        "overall_status": overall_status,
        "blockers": blockers,
        "warnings": warnings,
        "line_checks": line_checks,
        "summary_counts": {
            "line_count": len(purchase_order.lines),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "lines_with_blockers": sum(1 for line in line_checks if line["blockers"]),
            "lines_with_warnings": sum(1 for line in line_checks if line["warnings"]),
            "blocked_line_count": sum(1 for line in line_checks if line["blockers"]),
            "warning_line_count": sum(1 for line in line_checks if line["warnings"]),
            "legacy_line_count": sum(1 for line in line_checks if line["product_supplier_id"] is not None),
            "missing_cost_line_count": sum(1 for line in line_checks if not line["cost_present"]),
        },
    }


def line_preflight_check(
    db: Session,
    purchase_order: PurchaseOrder,
    line: PurchaseOrderLine,
    recommendation: Recommendation | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    product: Product | None = line.product
    quantity = line.quantity
    estimated_line_total = line.line_total
    if estimated_line_total is None and line.unit_cost is not None and quantity is not None:
        estimated_line_total = round(float(quantity) * float(line.unit_cost), 2)

    if line.product_id is None:
        blockers.append("Line has no product_id; canonical product validation cannot be performed.")
    if product is None:
        blockers.append("Line product is missing.")
    else:
        if product.is_non_inventory:
            blockers.append("Line product is non-inventory.")
        if product.supplier_id is None:
            blockers.append("Line product is missing a canonical supplier assignment.")
        elif purchase_order.supplier_id is not None and product.supplier_id != purchase_order.supplier_id:
            blockers.append("Line product canonical supplier conflicts with the PO supplier.")
        if line.supplier_product_name and line.supplier_product_name != product.name:
            warnings.append("Line product name snapshot differs from the current product name.")

    if quantity is None or quantity <= 0:
        blockers.append("Line quantity must be greater than zero.")

    cost_present = line.unit_cost is not None
    if not cost_present:
        if settings.recommendation_require_cost:
            blockers.append("Line unit cost is missing and cost is required.")
        else:
            warnings.append("Line unit cost is missing.")

    if line.pack_size is None:
        if settings.recommendation_require_pack_size:
            blockers.append("Line pack size is missing and pack size is required.")
        else:
            warnings.append("Line pack size is missing.")

    if line.minimum_order_quantity is None or line.minimum_order_quantity <= 0:
        warnings.append("Line minimum order quantity is missing; fallback MOQ may have been used.")
    if not line.supplier_sku:
        warnings.append("Line supplier SKU is missing.")
    if line.product_supplier_id is not None:
        warnings.append("Line uses legacy ProductSupplier snapshot for backward compatibility.")

    if recommendation and is_manager_approved_stale_recommendation(recommendation):
        warnings.append("Line originated from a manager-approved one-time stale-demand recommendation.")

    canonical_supplier_id = product.supplier_id if product else None
    supplier_name = product.supplier_record.name if product and product.supplier_record else None
    return {
        "line_id": line.id,
        "product_id": line.product_id,
        "product_name": product.name if product else line.supplier_product_name,
        "supplier_id": canonical_supplier_id,
        "supplier_name": supplier_name,
        "quantity": quantity,
        "unit_cost": line.unit_cost,
        "estimated_line_total": estimated_line_total,
        "product_supplier_id": line.product_supplier_id,
        "source_recommendation_id": recommendation.id if recommendation else None,
        "is_inventory_product": bool(product and not product.is_non_inventory),
        "canonical_supplier_id": canonical_supplier_id,
        "canonical_supplier_matches_po_supplier": bool(
            product
            and product.supplier_id is not None
            and purchase_order.supplier_id is not None
            and product.supplier_id == purchase_order.supplier_id
        ),
        "quantity_valid": quantity is not None and quantity > 0,
        "cost_present": cost_present,
        "supplier_snapshot_present": bool(line.supplier_sku or line.supplier_product_name),
        "blockers": unique_preserve_order(blockers),
        "warnings": unique_preserve_order(warnings),
    }


def is_manager_approved_stale_recommendation(recommendation: Recommendation) -> bool:
    forecast_snapshot = recommendation.forecast_snapshot or {}
    return (
        bool(forecast_snapshot.get("stale_demand_only"))
        and forecast_snapshot.get("review_decision") == "manager_approved_one_time"
    )


def assert_preflight_allows(preflight: dict[str, Any], transition: str) -> None:
    allowed_key = {
        "submit": "can_submit",
        "approve": "can_approve",
        "issue": "can_issue_if_applicable",
    }[transition]
    if preflight[allowed_key]:
        return
    if preflight["blockers"]:
        detail = "; ".join(preflight["blockers"])
    elif transition == "submit":
        detail = "Only draft purchase orders can be submitted for approval."
    elif transition == "approve":
        detail = "Only pending approval purchase orders can be approved."
    else:
        detail = "Only approved purchase orders can be issued."
    raise ValueError(f"Purchase order preflight failed: {detail}")
