from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.recommendation import Recommendation
from app.routes.purchase_orders import serialize_purchase_order
from app.schemas.recommendation import (
    RecommendationAcceptRequest,
    RecommendationConvertResponse,
    RecommendationRejectRequest,
    RecommendationResponse,
)
from app.schemas.llm import LLMRecommendationExplanationResponse
from app.services.llm_recommendation_service import (
    LLMRecommendationError,
    generate_llm_explanation_for_recommendation,
)
from app.services.recommendations import (
    RecommendationError,
    accept_recommendation,
    convert_recommendation_to_draft_po,
    create_reorder_recommendation_for_product,
    reject_recommendation,
)
from app.services.recommendation_audit import (
    audit_existing_recommendations,
    demand_policy_impact,
    explain_product_recommendation,
)
from app.services.perf_logging import perf_timer


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def serialize_recommendation(recommendation: Recommendation) -> dict:
    return {
        "id": recommendation.id,
        "product_id": recommendation.product_id,
        "product_name": recommendation.product.name if recommendation.product else None,
        "supplier_id": recommendation.supplier_id,
        "supplier_name": recommendation.supplier.name if recommendation.supplier else None,
        "product_supplier_id": recommendation.product_supplier_id,
        "converted_purchase_order_id": recommendation.converted_purchase_order_id,
        "recommendation_type": recommendation.recommendation_type,
        "status": recommendation.status,
        "recommended_quantity": recommendation.recommended_qty,
        "recommended_supplier_name": recommendation.recommended_supplier_name,
        "recommended_supplier_sku": recommendation.recommended_supplier_sku,
        "estimated_unit_cost": recommendation.estimated_unit_cost,
        "estimated_total_cost": recommendation.estimated_total_cost,
        "currency": recommendation.currency,
        "reason": recommendation.reason,
        "confidence": recommendation.confidence,
        "input_snapshot": recommendation.input_snapshot,
        "forecast_snapshot": recommendation.forecast_snapshot,
        "supplier_context_snapshot": recommendation.supplier_context_snapshot,
        "model_name": recommendation.model_name,
        "prompt_version": recommendation.prompt_version,
        "generated_by": recommendation.generated_by,
        "reviewed_by": recommendation.reviewed_by,
        "reviewed_at": recommendation.reviewed_at,
        "rejected_reason": recommendation.rejected_reason,
        "created_at": recommendation.created_at,
        "updated_at": recommendation.updated_at,
    }


def recommendation_query(db: Session):
    return db.query(Recommendation).options(
        selectinload(Recommendation.product),
        selectinload(Recommendation.supplier),
        selectinload(Recommendation.product_supplier),
    )


def load_recommendation(db: Session, recommendation_id: int) -> Recommendation:
    recommendation = recommendation_query(db).filter(Recommendation.id == recommendation_id).first()
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return recommendation


@router.post("/reorder/{product_id}", response_model=RecommendationResponse, status_code=201)
def create_reorder_recommendation(product_id: int, db: Session = Depends(get_db)):
    try:
        recommendation = create_reorder_recommendation_for_product(db, product_id)
    except RecommendationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return serialize_recommendation(load_recommendation(db, recommendation.id))


@router.get("", response_model=list[RecommendationResponse])
def list_recommendations(db: Session = Depends(get_db)):
    with perf_timer("recommendations.list") as perf:
        recommendations = recommendation_query(db).order_by(Recommendation.id.asc()).all()
        perf["returned"] = len(recommendations)
        return [serialize_recommendation(recommendation) for recommendation in recommendations]


@router.get("/audit")
def audit_recommendations(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return audit_existing_recommendations(db, limit=limit)


@router.get("/explain")
def explain_recommendation(product_id: int = Query(..., ge=1), db: Session = Depends(get_db)):
    explanation = explain_product_recommendation(db, product_id)
    if explanation is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return explanation


@router.get("/demand-policy-impact")
def get_demand_policy_impact(
    lookback_days: str = Query(default="all", pattern="^(90|180|365|all)$"),
    quantity_mode: str = Query(default="net_qty", pattern="^(qty_used|net_qty)$"),
    stale_days: int = Query(default=180, ge=1, le=3650),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    parsed_lookback = -1 if lookback_days == "all" else int(lookback_days)
    return demand_policy_impact(
        db,
        lookback_days=parsed_lookback,
        quantity_mode=quantity_mode,
        stale_days=stale_days,
        limit=limit,
    )


@router.get("/{recommendation_id}", response_model=RecommendationResponse)
def get_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    return serialize_recommendation(load_recommendation(db, recommendation_id))


@router.post("/{recommendation_id}/accept", response_model=RecommendationResponse)
def accept_recommendation_route(
    recommendation_id: int,
    payload: RecommendationAcceptRequest | None = None,
    db: Session = Depends(get_db),
):
    recommendation = load_recommendation(db, recommendation_id)
    try:
        updated = accept_recommendation(db, recommendation, reviewed_by=payload.reviewed_by if payload else None)
    except RecommendationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return serialize_recommendation(load_recommendation(db, updated.id))


@router.post("/{recommendation_id}/reject", response_model=RecommendationResponse)
def reject_recommendation_route(
    recommendation_id: int,
    payload: RecommendationRejectRequest | None = None,
    db: Session = Depends(get_db),
):
    recommendation = load_recommendation(db, recommendation_id)
    try:
        updated = reject_recommendation(
            db,
            recommendation,
            rejected_reason=payload.rejected_reason if payload else None,
            reviewed_by=payload.reviewed_by if payload else None,
        )
    except RecommendationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return serialize_recommendation(load_recommendation(db, updated.id))


@router.post("/{recommendation_id}/convert-to-draft-po", response_model=RecommendationConvertResponse)
def convert_recommendation_to_draft_po_route(
    recommendation_id: int,
    db: Session = Depends(get_db),
):
    recommendation = load_recommendation(db, recommendation_id)
    try:
        updated, po = convert_recommendation_to_draft_po(db, recommendation)
    except RecommendationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return {
        "recommendation": serialize_recommendation(load_recommendation(db, updated.id)),
        "purchase_order": serialize_purchase_order(po),
    }


@router.post("/{recommendation_id}/generate-llm-explanation", response_model=LLMRecommendationExplanationResponse)
def generate_llm_explanation_route(
    recommendation_id: int,
    db: Session = Depends(get_db),
):
    try:
        return generate_llm_explanation_for_recommendation(db, recommendation_id)
    except LLMRecommendationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
