from app.models.purchase_order import PurchaseOrder
from app.models.recommendation import Recommendation
from app.services.llm_provider import MockLLMProvider
from app.services.llm_recommendation_service import (
    LLMRecommendationError,
    generate_llm_explanation_for_recommendation,
    validate_llm_explanation_output,
)
from tests.test_recommendations import create_recommendation, seed_recommendation_product


class InvalidActionProvider(MockLLMProvider):
    def generate_purchase_recommendation_explanation(self, input_data):
        output = super().generate_purchase_recommendation_explanation(input_data)
        output["suggested_action"] = "approve_purchase_order"
        return output


class InvalidConfidenceProvider(MockLLMProvider):
    def generate_purchase_recommendation_explanation(self, input_data):
        output = super().generate_purchase_recommendation_explanation(input_data)
        output["confidence"] = 1.5
        return output


def test_invalid_llm_action_is_rejected_by_guardrails():
    payload = MockLLMProvider().generate_purchase_recommendation_explanation(
        {"recommended_quantity": 1, "forecast_snapshot": {}, "supplier_context_snapshot": {}}
    )
    payload["suggested_action"] = "issue_purchase_order"

    try:
        validate_llm_explanation_output(payload)
    except Exception as error:
        assert "forbidden" in str(error)
    else:
        raise AssertionError("Expected invalid LLM action to be rejected.")


def test_invalid_confidence_is_rejected():
    payload = MockLLMProvider().generate_purchase_recommendation_explanation(
        {"recommended_quantity": 1, "forecast_snapshot": {}, "supplier_context_snapshot": {}}
    )
    payload["confidence"] = -0.1

    try:
        validate_llm_explanation_output(payload)
    except Exception as error:
        assert "confidence" in str(error)
    else:
        raise AssertionError("Expected invalid LLM confidence to be rejected.")


def test_generate_llm_explanation_updates_only_safe_recommendation_fields(db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = Recommendation(
        product_id=product.id,
        supplier_id=None,
        product_supplier_id=None,
        recommended_qty=4,
        status="pending_review",
        risk_level="low",
        forecast_snapshot={"recommended_qty": 4},
        supplier_context_snapshot={"supplier_name": "Recommendation Supplier", "supplier_sku": "REC-SKU"},
    )
    db_session.add(recommendation)
    db_session.commit()

    output = generate_llm_explanation_for_recommendation(
        db_session,
        recommendation.id,
        provider=MockLLMProvider(),
    )

    db_session.refresh(recommendation)
    assert output["suggested_action"] == "reorder"
    assert recommendation.reason == output["explanation"]
    assert recommendation.explanation == output["explanation"]
    assert recommendation.confidence == output["confidence"]
    assert recommendation.model_name == "mock"
    assert recommendation.prompt_version == "mock-v1"
    assert recommendation.status == "pending_review"
    assert recommendation.converted_purchase_order_id is None
    assert db_session.query(PurchaseOrder).count() == 0


def test_generate_llm_explanation_does_not_change_recommendation_status(client, db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = create_recommendation(client, product.id)

    response = client.post(f"/recommendations/{recommendation['id']}/generate-llm-explanation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "mock"
    updated = db_session.get(Recommendation, recommendation["id"])
    assert updated.status == "pending_review"
    assert updated.model_name == "mock"
    assert db_session.query(PurchaseOrder).count() == 0


def test_generate_llm_explanation_missing_recommendation_returns_404(client):
    response = client.post("/recommendations/999/generate-llm-explanation")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recommendation not found."


def test_generate_llm_explanation_rejects_forbidden_provider_output(db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = Recommendation(
        product_id=product.id,
        recommended_qty=4,
        status="pending_review",
        risk_level="low",
    )
    db_session.add(recommendation)
    db_session.commit()

    try:
        generate_llm_explanation_for_recommendation(
            db_session,
            recommendation.id,
            provider=InvalidActionProvider(),
        )
    except LLMRecommendationError as error:
        assert error.status_code == 400
        assert "forbidden" in error.message
    else:
        raise AssertionError("Expected forbidden provider output to be rejected.")


def test_generate_llm_explanation_rejects_invalid_confidence(db_session):
    product, _supplier, _mapping = seed_recommendation_product(db_session)
    recommendation = Recommendation(
        product_id=product.id,
        recommended_qty=4,
        status="pending_review",
        risk_level="low",
    )
    db_session.add(recommendation)
    db_session.commit()

    try:
        generate_llm_explanation_for_recommendation(
            db_session,
            recommendation.id,
            provider=InvalidConfidenceProvider(),
        )
    except LLMRecommendationError as error:
        assert error.status_code == 400
        assert "confidence" in error.message
    else:
        raise AssertionError("Expected invalid provider confidence to be rejected.")
