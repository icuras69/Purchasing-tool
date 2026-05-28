from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.recommendation import Recommendation
from app.services.ai_guardrails import (
    AIGuardrailViolation,
    ensure_ai_cannot_approve_or_issue,
    sanitize_ai_explanation,
)
from app.services.llm_provider import LLMProvider, get_llm_provider


LLM_SUGGESTED_ACTIONS = {"reorder", "wait", "review"}


class LLMRecommendationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def build_recommendation_llm_input(recommendation: Recommendation) -> dict[str, Any]:
    return {
        "recommendation_id": recommendation.id,
        "product_id": recommendation.product_id,
        "product": {
            "id": recommendation.product.id,
            "name": recommendation.product.name,
        }
        if recommendation.product
        else None,
        "supplier_id": recommendation.supplier_id,
        "product_supplier_id": recommendation.product_supplier_id,
        "recommended_quantity": recommendation.recommended_qty,
        "recommended_supplier_name": recommendation.recommended_supplier_name,
        "recommended_supplier_sku": recommendation.recommended_supplier_sku,
        "estimated_unit_cost": recommendation.estimated_unit_cost,
        "estimated_total_cost": recommendation.estimated_total_cost,
        "currency": recommendation.currency,
        "input_snapshot": recommendation.input_snapshot,
        "forecast_snapshot": recommendation.forecast_snapshot,
        "supplier_context_snapshot": recommendation.supplier_context_snapshot,
    }


def validate_llm_explanation_output(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AIGuardrailViolation("LLM explanation output must be an object.")

    required_fields = {
        "suggested_action",
        "summary",
        "explanation",
        "risk_flags",
        "missing_data_warnings",
        "confidence",
        "structured_data_citations",
    }
    missing = sorted(required_fields - set(data))
    if missing:
        raise AIGuardrailViolation(f"LLM explanation output is missing fields: {', '.join(missing)}")

    suggested_action = str(data.get("suggested_action") or "").strip().lower()
    ensure_ai_cannot_approve_or_issue(suggested_action)
    if suggested_action not in LLM_SUGGESTED_ACTIONS:
        raise AIGuardrailViolation(f"LLM suggested action is not allowed: {suggested_action}")

    confidence = data.get("confidence")
    if not isinstance(confidence, int | float) or confidence < 0 or confidence > 1:
        raise AIGuardrailViolation("LLM confidence must be a number between 0 and 1.")

    if not isinstance(data.get("risk_flags"), list):
        raise AIGuardrailViolation("LLM risk_flags must be a list.")
    if not isinstance(data.get("missing_data_warnings"), list):
        raise AIGuardrailViolation("LLM missing_data_warnings must be a list.")
    if not isinstance(data.get("structured_data_citations"), list):
        raise AIGuardrailViolation("LLM structured_data_citations must be a list.")

    return {
        "suggested_action": suggested_action,
        "summary": sanitize_ai_explanation(data.get("summary")),
        "explanation": sanitize_ai_explanation(data.get("explanation")),
        "risk_flags": [str(flag) for flag in data.get("risk_flags")],
        "missing_data_warnings": [str(warning) for warning in data.get("missing_data_warnings")],
        "confidence": float(confidence),
        "structured_data_citations": [str(citation) for citation in data.get("structured_data_citations")],
    }


def load_recommendation_for_llm(db: Session, recommendation_id: int) -> Recommendation | None:
    return (
        db.query(Recommendation)
        .options(
            selectinload(Recommendation.product),
            selectinload(Recommendation.supplier),
            selectinload(Recommendation.product_supplier),
        )
        .filter(Recommendation.id == recommendation_id)
        .first()
    )


def generate_llm_explanation_for_recommendation(
    db: Session,
    recommendation_id: int,
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    recommendation = load_recommendation_for_llm(db, recommendation_id)
    if not recommendation:
        raise LLMRecommendationError("Recommendation not found.", status_code=404)

    provider = provider or get_llm_provider(settings.llm_provider, settings.enable_real_llm)
    input_data = build_recommendation_llm_input(recommendation)

    try:
        output = validate_llm_explanation_output(
            provider.generate_purchase_recommendation_explanation(input_data)
        )
    except (AIGuardrailViolation, ValueError) as error:
        raise LLMRecommendationError(str(error), status_code=400) from error

    recommendation.reason = output["explanation"]
    recommendation.explanation = output["explanation"]
    recommendation.confidence = output["confidence"]
    recommendation.model_name = provider.model_name
    recommendation.prompt_version = provider.prompt_version
    recommendation.updated_at = datetime.utcnow()
    db.commit()

    return {
        **output,
        "model_name": provider.model_name,
        "prompt_version": provider.prompt_version,
    }
