from datetime import date, datetime
from math import ceil
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder
from app.models.recommendation import Recommendation
from app.services.forecast_input_reconciliation import profile_or_effective_inputs
from app.services.recommendation_audit import (
    explain_product_recommendation,
    validate_product_can_create_reorder_recommendation,
)
from app.services.purchase_order_drafting import (
    recalculate_purchase_order_total,
    snapshot_purchase_order_line_from_product,
)


PENDING_REVIEW = "pending_review"
ACCEPTED = "accepted"
REJECTED = "rejected"
CONVERTED_TO_PO = "converted_to_po"
REORDER = "reorder"
MANAGER_APPROVED_ONE_TIME = "manager_approved_one_time"


class RecommendationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def load_product_for_recommendation(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.inventory_positions),
        )
        .filter(Product.id == product_id)
        .first()
    )


def create_reorder_recommendation_for_product(
    db: Session,
    product_id: int,
    *,
    generated_by: str = "system",
) -> Recommendation:
    product = load_product_for_recommendation(db, product_id)
    if not product:
        raise RecommendationError("Product not found.", status_code=404)
    if not product.is_active:
        raise RecommendationError("Inactive products cannot receive new reorder recommendations.")

    explanation = explain_product_recommendation(db, product.id)
    if explanation is None:
        raise RecommendationError("Product not found.", status_code=404)
    try:
        validate_product_can_create_reorder_recommendation(explanation)
    except ValueError as error:
        raise RecommendationError(str(error)) from error

    forecast = dict(explanation["forecast_snapshot"])
    forecast.update(
        {
            "purchase_readiness_status": explanation.get("purchase_readiness_status"),
            "purchase_readiness_issues": explanation.get("purchase_readiness_issues"),
            "suggested_cleanup_action": explanation.get("suggested_cleanup_action"),
            "not_ready_for_po": explanation.get("not_ready_for_po"),
            "quantity_review_note": explanation.get("quantity_review_note"),
            "quantity_satisfies_moq": explanation.get("quantity_satisfies_moq"),
            "quantity_satisfies_pack_size": explanation.get("quantity_satisfies_pack_size"),
            "quantity_was_raised_to_moq": explanation.get("quantity_was_raised_to_moq"),
            "quantity_was_rounded_to_pack_size": explanation.get("quantity_was_rounded_to_pack_size"),
            "pack_size_required": explanation.get("pack_size_required"),
            "cost_required": explanation.get("cost_required"),
            "cost_status": explanation.get("cost_status"),
            "stale_demand_policy": explanation.get("stale_demand_policy"),
            "stale_demand_recommendations_allowed": explanation.get("stale_demand_recommendations_allowed"),
            "review_decision": explanation.get("review_decision"),
            "reviewed_by": explanation.get("reviewed_by"),
            "review_notes": explanation.get("review_notes"),
            "reviewed_at": explanation.get("reviewed_at"),
            "decision_status": explanation.get("decision_status"),
        }
    )
    supplier_context = forecast.get("supplier_context") or {}
    if supplier_context.get("mapping_source") != "orderpro_product_supplier":
        raise RecommendationError("Product is missing a canonical supplier assignment.")

    quantity = recommended_quantity(forecast, product)
    effective_inputs = profile_or_effective_inputs(db, product)
    unit_cost = effective_inputs["cost_price"]
    estimated_total_cost = round(quantity * unit_cost, 2) if unit_cost is not None else None
    now = datetime.utcnow()
    supplier = product.supplier_record
    needs_mapping = bool(supplier_context.get("needs_supplier_mapping"))

    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=product.supplier_id,
        product_supplier_id=None,
        generated_at=now,
        created_at=now,
        updated_at=now,
        recommended_qty=quantity,
        risk_level=forecast.get("risk_level") or "low",
        explanation=forecast.get("explanation"),
        recommendation_type=REORDER,
        status=PENDING_REVIEW,
        recommended_supplier_name=supplier.name if supplier else product.supplier,
        recommended_supplier_sku=product.supplier_sku,
        estimated_unit_cost=unit_cost,
        estimated_total_cost=estimated_total_cost,
        currency=None,
        reason=recommendation_reason(forecast, needs_mapping),
        confidence=None,
        input_snapshot=input_snapshot(product, supplier_context, forecast, effective_inputs),
        forecast_snapshot=json_safe_snapshot(forecast),
        supplier_context_snapshot=json_safe_snapshot(supplier_context),
        model_name=None,
        prompt_version=None,
        generated_by=generated_by,
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation


def recommended_quantity(forecast: dict[str, Any], product: Product) -> float:
    quantity = float(forecast.get("recommended_qty") or 0)
    if quantity <= 0 and forecast.get("incoming_qty", 0) > 0:
        return 0.0
    if quantity <= 0:
        quantity = float(product.min_order_qty or 1)

    if product.min_order_qty and quantity < product.min_order_qty:
        quantity = float(product.min_order_qty)

    return float(ceil(quantity)) if quantity > 0 else 1.0


def recommendation_reason(forecast: dict[str, Any], needs_mapping: bool) -> str | None:
    explanation = forecast.get("explanation")
    if needs_mapping:
        mapping_note = "Structured OrderPro supplier mapping is missing and should be reviewed before purchasing."
        return f"{explanation} {mapping_note}" if explanation else mapping_note
    return explanation


def input_snapshot(
    product: Product,
    supplier_context: dict[str, Any],
    forecast: dict[str, Any] | None = None,
    effective_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    forecast = forecast or {}
    effective_inputs = effective_inputs or {}
    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "orderpro_id": product.orderpro_id,
            "orderpro_sku": product.orderpro_sku,
            "supplier_id": product.supplier_id,
            "supplier_sku": product.supplier_sku,
            "current_stock": product.current_stock,
            "safety_stock": product.safety_stock,
            "lead_time_days": product.lead_time_days,
            "min_order_qty": product.min_order_qty,
            "cost_price": product.cost_price,
            "source_system": product.source_system,
        },
        "effective_forecast_inputs": {
            "cost_price": effective_inputs.get("cost_price", forecast.get("cost_price")),
            "cost_source": effective_inputs.get("cost_source", forecast.get("cost_source")),
            "cost_confidence": effective_inputs.get("cost_confidence", forecast.get("cost_confidence")),
            "lead_time_days": effective_inputs.get("lead_time_days", forecast.get("lead_time_days_used")),
            "lead_time_source": effective_inputs.get("lead_time_source", forecast.get("lead_time_source")),
            "min_order_qty": effective_inputs.get("min_order_qty"),
            "moq_source": effective_inputs.get("moq_source", forecast.get("moq_source")),
            "pack_size": effective_inputs.get("pack_size", forecast.get("pack_size")),
            "pack_size_source": effective_inputs.get("pack_size_source", forecast.get("pack_size_source")),
            "pack_size_required": forecast.get("pack_size_required"),
            "pack_rule_context": forecast.get("pack_rule_context"),
            "raw_required_quantity": forecast.get("raw_required_quantity"),
            "pre_pack_recommended_quantity": forecast.get("pre_pack_recommended_quantity"),
            "order_multiple": forecast.get("order_multiple"),
            "pack_rule_name": forecast.get("pack_rule_name"),
            "pack_rule_source": forecast.get("pack_rule_source"),
            "pack_rule_display": forecast.get("pack_rule_display"),
            "pack_rounding_explanation": forecast.get("pack_rounding_explanation"),
            "safety_stock": effective_inputs.get("safety_stock", forecast.get("safety_stock_used")),
            "safety_stock_source": effective_inputs.get("safety_stock_source", forecast.get("safety_stock_source")),
            "cost_required": forecast.get("cost_required"),
        },
        "orderpro_product_supplier": {
            "supplier_id": product.supplier_id,
            "supplier_name": supplier_context.get("supplier_name"),
            "supplier_code": supplier_context.get("supplier_code"),
            "supplier_sku": product.supplier_sku,
            "mapping_source": supplier_context.get("mapping_source"),
            "has_supplier_mapping": supplier_context.get("has_supplier_mapping"),
            "needs_supplier_mapping": supplier_context.get("needs_supplier_mapping"),
        },
        "inbound_stock": {
            "incoming_qty": forecast.get("incoming_qty", 0),
            "open_po_count": (forecast.get("incoming_stock_context") or {}).get("open_po_count", 0),
            "recommended_qty_before_inbound": forecast.get("recommended_qty_before_inbound"),
            "recommended_qty_after_inbound": forecast.get("recommended_qty_after_inbound"),
            "inbound_adjustment_qty": forecast.get("inbound_adjustment_qty"),
        },
    }


def json_safe_snapshot(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe_snapshot(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe_snapshot(child) for child in value]
    return value


def accept_recommendation(
    db: Session,
    recommendation: Recommendation,
    *,
    reviewed_by: str | None = None,
) -> Recommendation:
    if recommendation.status == REJECTED:
        raise RecommendationError("Rejected recommendations cannot be accepted.")
    if recommendation.status == CONVERTED_TO_PO:
        raise RecommendationError("Converted recommendations cannot be accepted again.")

    recommendation.status = ACCEPTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = datetime.utcnow()
    recommendation.updated_at = recommendation.reviewed_at
    db.commit()
    db.refresh(recommendation)
    return recommendation


def reject_recommendation(
    db: Session,
    recommendation: Recommendation,
    *,
    rejected_reason: str | None = None,
    reviewed_by: str | None = None,
) -> Recommendation:
    if recommendation.status == CONVERTED_TO_PO:
        raise RecommendationError("Converted recommendations cannot be rejected.")

    now = datetime.utcnow()
    recommendation.status = REJECTED
    recommendation.reviewed_by = reviewed_by
    recommendation.reviewed_at = now
    recommendation.rejected_reason = rejected_reason
    recommendation.updated_at = now
    db.commit()
    db.refresh(recommendation)
    return recommendation


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def recommendation_po_readiness(db: Session, recommendation: Recommendation) -> dict[str, Any]:
    product = load_product_for_recommendation(db, recommendation.product_id) if recommendation.product_id else None
    explanation = explain_product_recommendation(db, product.id) if product else None
    supplier = product.supplier_record if product else None
    blockers: list[str] = []
    warnings: list[str] = []
    required_manager_decision: str | None = None
    canonical_supplier_check_result = "missing"
    po_supplier_source = "products.supplier_id"

    quantity = float(recommendation.recommended_qty or 0)
    if recommendation.status != ACCEPTED:
        blockers.append("Only accepted recommendations can be converted to a draft purchase order.")
    if recommendation.converted_purchase_order_id:
        blockers.append("Recommendation has already been converted to a purchase order.")
    if recommendation.recommendation_type != REORDER:
        blockers.append("Recommendation type is not reorder.")
    if quantity <= 0:
        blockers.append("Recommendation quantity must be greater than zero.")

    if product is None:
        blockers.append("Product not found.")
    else:
        if not product.is_active:
            blockers.append("Product is inactive.")
        if product.is_non_inventory:
            blockers.append("Product is non-inventory.")
        if product.supplier_id is None or supplier is None:
            blockers.append("Product is missing a canonical supplier assignment.")
            canonical_supplier_check_result = "missing"
        elif hasattr(supplier, "is_active") and not supplier.is_active:
            blockers.append("Canonical supplier is inactive.")
            canonical_supplier_check_result = "inactive"
        elif recommendation.supplier_id is not None and recommendation.supplier_id != product.supplier_id:
            blockers.append("Recommendation supplier conflicts with the product canonical supplier.")
            canonical_supplier_check_result = "conflict"
        else:
            canonical_supplier_check_result = "ok"

    if explanation is None and product is not None:
        blockers.append("Recommendation explanation is unavailable.")
    elif explanation:
        explanation_blockers = set(explanation.get("blockers") or [])
        if "Missing supplier" in explanation_blockers and "Product is missing a canonical supplier assignment." not in blockers:
            blockers.append("Product is missing a canonical supplier assignment.")
        if "Missing lead time" in explanation_blockers:
            blockers.append("Product is missing usable supplier lead time.")
        if "No demand history" in explanation_blockers:
            blockers.append("Product is missing demand history or open demand.")
        if "Product is non-inventory" in explanation_blockers and "Product is non-inventory." not in blockers:
            blockers.append("Product is non-inventory.")

        if explanation.get("recommended_action") != "reorder":
            blockers.append("Forecast action is not reorder.")

        stale_only = bool(explanation.get("stale_demand_only"))
        manager_approved = explanation.get("review_decision") == MANAGER_APPROVED_ONE_TIME
        if stale_only:
            required_manager_decision = MANAGER_APPROVED_ONE_TIME
            if not manager_approved:
                blockers.append("Stale-only demand requires manager-approved one-time review before PO creation.")
            else:
                warnings.append("Stale-only demand was manager-approved for one-time PO review.")

        if explanation.get("cost_required") and explanation.get("cost_status") == "missing":
            blockers.append("Product is missing required cost.")
        if explanation.get("pack_size_required") and explanation.get("pack_size") is None:
            blockers.append("Product is missing required pack size.")

        for warning in explanation.get("warnings") or []:
            if str(warning).startswith("Stale demand only") and required_manager_decision == MANAGER_APPROVED_ONE_TIME:
                continue
            warnings.append(str(warning))
        for issue in explanation.get("purchase_readiness_issues") or []:
            if issue in {"Stale-only demand requires manual review", "Missing supplier", "Missing lead time", "No demand history"}:
                continue
            if issue == "Missing cost" and explanation.get("cost_required"):
                continue
            if issue == "Missing pack size" and explanation.get("pack_size_required"):
                continue
            warnings.append(str(issue))

    unit_cost = recommendation.estimated_unit_cost
    if unit_cost is None and product is not None:
        unit_cost = profile_or_effective_inputs(db, product).get("cost_price")
    estimated_total_cost = round(quantity * unit_cost, 2) if unit_cost is not None and quantity > 0 else None
    blockers = unique_preserve_order(blockers)
    warnings = unique_preserve_order(warnings)
    return {
        "recommendation_id": recommendation.id,
        "product_id": product.id if product else recommendation.product_id,
        "product_name": product.name if product else None,
        "supplier_id": product.supplier_id if product else None,
        "supplier_name": supplier.name if supplier else None,
        "recommendation_status": recommendation.status,
        "recommendation_type": recommendation.recommendation_type,
        "recommended_quantity": quantity,
        "estimated_unit_cost": unit_cost,
        "estimated_total_cost": estimated_total_cost,
        "can_create_draft_po": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "required_manager_decision": required_manager_decision,
        "po_supplier_source": po_supplier_source,
        "canonical_supplier_check_result": canonical_supplier_check_result,
        "product_supplier_id": recommendation.product_supplier_id,
        "recommendation_supplier_id": recommendation.supplier_id,
        "forecast_recommended_action": explanation.get("recommended_action") if explanation else None,
        "stale_demand_only": bool(explanation.get("stale_demand_only")) if explanation else False,
        "review_decision": explanation.get("review_decision") if explanation else None,
        "purchase_readiness_status": explanation.get("purchase_readiness_status") if explanation else None,
    }


def convert_recommendation_to_draft_po(
    db: Session,
    recommendation: Recommendation,
) -> tuple[Recommendation, PurchaseOrder]:
    readiness = recommendation_po_readiness(db, recommendation)
    if not readiness["can_create_draft_po"]:
        raise RecommendationError("; ".join(readiness["blockers"]))

    product = load_product_for_recommendation(db, recommendation.product_id)
    if not product or not product.supplier_id:
        raise RecommendationError("Product is missing a canonical supplier assignment.")

    now = datetime.utcnow()
    po = PurchaseOrder(
        supplier_id=product.supplier_id,
        status="draft",
        created_at=now,
        updated_at=now,
        notes=f"Draft converted from recommendation {recommendation.id}",
        created_by=recommendation.reviewed_by or recommendation.generated_by,
    )
    db.add(po)
    db.flush()
    po.lines.append(
        snapshot_purchase_order_line_from_product(
            po,
            product,
            recommendation.recommended_qty,
            notes=f"Drafted from accepted recommendation {recommendation.id}.",
        )
    )
    db.flush()
    recalculate_purchase_order_total(po)

    recommendation.status = CONVERTED_TO_PO
    recommendation.converted_purchase_order_id = po.id
    recommendation.updated_at = now
    db.commit()
    db.refresh(recommendation)
    db.refresh(po)
    return recommendation, po
