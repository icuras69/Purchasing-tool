import pytest

from app.services.ai_guardrails import (
    ALLOWED_AI_ACTIONS,
    AIGuardrailViolation,
    sanitize_ai_explanation,
    validate_ai_recommendation_action,
    validate_recommendation_output_shape,
)


def valid_output() -> dict:
    return {
        "recommendation_summary": "Order soon.",
        "risk_flags": ["low_stock"],
        "confidence": 0.75,
        "suggested_action": "create_recommendation_draft",
        "explanation": " Stock is below reorder point. ",
        "missing_data_warnings": [],
        "cited_fields": ["forecast.recommended_qty"],
    }


@pytest.mark.parametrize("action", sorted(ALLOWED_AI_ACTIONS))
def test_allowed_ai_actions_pass_validation(action):
    assert validate_ai_recommendation_action(action) == action


@pytest.mark.parametrize(
    "action",
    [
        "approve_purchase_order",
        "issue_purchase_order",
        "receive_purchase_order",
        "delete_mapping",
        "update_inventory",
        "place_external_order",
        "bypass_approval",
    ],
)
def test_forbidden_ai_actions_are_rejected(action):
    with pytest.raises(AIGuardrailViolation):
        validate_ai_recommendation_action(action)


@pytest.mark.parametrize("action", ["", "invent_supplier", "approve", "issue", "receive"])
def test_unknown_or_unsafe_actions_are_rejected(action):
    with pytest.raises(AIGuardrailViolation):
        validate_ai_recommendation_action(action)


def test_recommendation_output_shape_accepts_valid_structured_output():
    sanitized = validate_recommendation_output_shape(valid_output())

    assert sanitized["explanation"] == "Stock is below reorder point."
    assert sanitized["confidence"] == 0.75


def test_recommendation_output_shape_rejects_missing_fields():
    output = valid_output()
    output.pop("cited_fields")

    with pytest.raises(AIGuardrailViolation):
        validate_recommendation_output_shape(output)


def test_recommendation_output_shape_rejects_bad_confidence():
    output = valid_output()
    output["confidence"] = 2

    with pytest.raises(AIGuardrailViolation):
        validate_recommendation_output_shape(output)


def test_sanitize_ai_explanation_handles_empty_or_unsafe_text():
    assert sanitize_ai_explanation(None) == ""
    assert sanitize_ai_explanation("  line one\x00\n line two  ") == "line one line two"
