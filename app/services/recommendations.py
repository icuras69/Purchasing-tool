from datetime import date, datetime
from math import ceil
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder
from app.models.recommendation import Recommendation
from app.services.forecasting import build_forecast
from app.services.purchase_order_drafting import (
    recalculate_purchase_order_total,
    snapshot_purchase_order_line,
)


PENDING_REVIEW = "pending_review"
ACCEPTED = "accepted"
REJECTED = "rejected"
CONVERTED_TO_PO = "converted_to_po"
REORDER = "reorder"


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

    forecast = build_forecast(db, product)
    supplier_context = forecast.get("supplier_context") or {}
    if supplier_context.get("mapping_source") == "missing":
        raise RecommendationError("Product is missing an OrderPro supplier mapping.")

    quantity = recommended_quantity(forecast, product)
    unit_cost = product.cost_price
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
        input_snapshot=input_snapshot(product, supplier_context, forecast),
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


def input_snapshot(product: Product, supplier_context: dict[str, Any], forecast: dict[str, Any] | None = None) -> dict[str, Any]:
    forecast = forecast or {}
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


def convert_recommendation_to_draft_po(
    db: Session,
    recommendation: Recommendation,
) -> tuple[Recommendation, PurchaseOrder]:
    if recommendation.status != ACCEPTED:
        raise RecommendationError("Only accepted recommendations can be converted to a draft purchase order.")
    if recommendation.converted_purchase_order_id:
        raise RecommendationError("Recommendation has already been converted to a purchase order.")
    if not recommendation.product_supplier_id or not recommendation.supplier_id:
        raise RecommendationError("Recommendation does not have a ProductSupplier mapping.")

    product_supplier = db.get(ProductSupplier, recommendation.product_supplier_id)
    if not product_supplier:
        raise RecommendationError("ProductSupplier mapping not found.")
    if product_supplier.match_status == REJECTED:
        raise RecommendationError("Rejected ProductSupplier mappings cannot be converted to purchase orders.")

    now = datetime.utcnow()
    po = PurchaseOrder(
        supplier_id=recommendation.supplier_id,
        status="draft",
        created_at=now,
        updated_at=now,
        notes=f"Draft converted from recommendation {recommendation.id}",
        created_by=recommendation.reviewed_by or recommendation.generated_by,
    )
    db.add(po)
    db.flush()
    po.lines.append(snapshot_purchase_order_line(po, product_supplier, recommendation.recommended_qty))
    db.flush()
    recalculate_purchase_order_total(po)

    recommendation.status = CONVERTED_TO_PO
    recommendation.converted_purchase_order_id = po.id
    recommendation.updated_at = now
    db.commit()
    db.refresh(recommendation)
    db.refresh(po)
    return recommendation, po
