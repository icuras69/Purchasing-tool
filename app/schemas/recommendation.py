from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.purchase_order import PurchaseOrderResponse


class RecommendationRejectRequest(BaseModel):
    rejected_reason: str | None = None
    reviewed_by: str | None = None


class RecommendationAcceptRequest(BaseModel):
    reviewed_by: str | None = None


class RecommendationResponse(BaseModel):
    id: int
    product_id: int
    product_name: str | None
    supplier_id: int | None
    supplier_name: str | None
    product_supplier_id: int | None
    converted_purchase_order_id: int | None
    recommendation_type: str
    status: str
    recommended_quantity: float
    recommended_supplier_name: str | None
    recommended_supplier_sku: str | None
    estimated_unit_cost: float | None
    estimated_total_cost: float | None
    currency: str | None
    reason: str | None
    confidence: float | None
    input_snapshot: dict[str, Any] | None
    forecast_snapshot: dict[str, Any] | None
    supplier_context_snapshot: dict[str, Any] | None
    model_name: str | None
    prompt_version: str | None
    generated_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejected_reason: str | None
    created_at: datetime
    updated_at: datetime


class RecommendationConvertResponse(BaseModel):
    recommendation: RecommendationResponse
    purchase_order: PurchaseOrderResponse
