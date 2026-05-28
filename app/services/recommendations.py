from datetime import datetime
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
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.master_items),
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

    product_supplier = select_safe_product_supplier(product)
    if not product_supplier:
        raise RecommendationError("Product does not have a valid ProductSupplier mapping.")

    forecast = build_forecast(db, product)
    supplier_context = forecast.get("supplier_context") or {}
    quantity = recommended_quantity(forecast, product_supplier)
    unit_cost = product_supplier.purchase_price
    estimated_total_cost = round(quantity * unit_cost, 2) if unit_cost is not None else None
    now = datetime.utcnow()

    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=product_supplier.supplier_id,
        product_supplier_id=product_supplier.id,
        generated_at=now,
        created_at=now,
        updated_at=now,
        recommended_qty=quantity,
        risk_level=forecast.get("risk_level") or "low",
        explanation=forecast.get("explanation"),
        recommendation_type=REORDER,
        status=PENDING_REVIEW,
        recommended_supplier_name=product_supplier.supplier.name if product_supplier.supplier else None,
        recommended_supplier_sku=product_supplier.supplier_sku,
        estimated_unit_cost=unit_cost,
        estimated_total_cost=estimated_total_cost,
        currency=product_supplier.currency,
        reason=forecast.get("explanation"),
        confidence=None,
        input_snapshot=input_snapshot(product, product_supplier),
        forecast_snapshot=forecast,
        supplier_context_snapshot=supplier_context,
        model_name=None,
        prompt_version=None,
        generated_by=generated_by,
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation


def select_safe_product_supplier(product: Product) -> ProductSupplier | None:
    mappings = [
        mapping for mapping in product.product_suppliers if mapping.match_status != REJECTED
    ]
    if not mappings:
        return None

    preferred = next(
        (
            mapping
            for mapping in mappings
            if mapping.is_preferred and mapping.match_status in {"confirmed", "matched"}
        ),
        None,
    )
    if preferred:
        return preferred

    confirmed_or_matched = [
        mapping for mapping in mappings if mapping.match_status in {"confirmed", "matched"}
    ]
    if confirmed_or_matched:
        return sorted(confirmed_or_matched, key=lambda mapping: mapping.id or 0)[0]

    return None


def recommended_quantity(forecast: dict[str, Any], product_supplier: ProductSupplier) -> float:
    quantity = float(forecast.get("recommended_qty") or 0)
    if quantity <= 0:
        quantity = float(product_supplier.minimum_order_quantity or 1)

    if product_supplier.minimum_order_quantity and quantity < product_supplier.minimum_order_quantity:
        quantity = float(product_supplier.minimum_order_quantity)

    if product_supplier.pack_size and product_supplier.pack_size > 0:
        pack_size = float(product_supplier.pack_size)
        quantity = ceil(quantity / pack_size) * pack_size

    return float(ceil(quantity)) if quantity > 0 else 1.0


def input_snapshot(product: Product, product_supplier: ProductSupplier) -> dict[str, Any]:
    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "current_stock": product.current_stock,
            "safety_stock": product.safety_stock,
            "lead_time_days": product.lead_time_days,
            "min_order_qty": product.min_order_qty,
        },
        "product_supplier": {
            "id": product_supplier.id,
            "supplier_id": product_supplier.supplier_id,
            "supplier_sku": product_supplier.supplier_sku,
            "supplier_product_name": product_supplier.supplier_product_name,
            "purchase_price": product_supplier.purchase_price,
            "currency": product_supplier.currency,
            "minimum_order_quantity": product_supplier.minimum_order_quantity,
            "pack_size": product_supplier.pack_size,
            "lead_time_days": product_supplier.lead_time_days,
            "match_status": product_supplier.match_status,
            "match_method": product_supplier.match_method,
        },
    }


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
