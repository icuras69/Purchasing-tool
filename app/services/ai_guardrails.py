from typing import Any


ALLOWED_AI_ACTIONS = {
    "explain_recommendation",
    "compare_suppliers",
    "suggest_reorder",
    "summarize_risk",
    "create_recommendation_draft",
}

FORBIDDEN_AI_ACTIONS = {
    "approve_purchase_order",
    "issue_purchase_order",
    "receive_purchase_order",
    "delete_mapping",
    "update_inventory",
    "place_external_order",
    "bypass_approval",
}

REQUIRED_RECOMMENDATION_OUTPUT_FIELDS = {
    "recommendation_summary",
    "risk_flags",
    "confidence",
    "suggested_action",
    "explanation",
    "missing_data_warnings",
    "cited_fields",
}

MAX_EXPLANATION_LENGTH = 4000


class AIGuardrailViolation(ValueError):
    pass


def validate_ai_recommendation_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if not normalized:
        raise AIGuardrailViolation("AI action is required.")
    ensure_ai_cannot_approve_or_issue(normalized)
    if normalized not in ALLOWED_AI_ACTIONS:
        raise AIGuardrailViolation(f"AI action is not allowed: {normalized}")
    return normalized


def ensure_ai_cannot_approve_or_issue(action: str) -> None:
    normalized = (action or "").strip().lower()
    if normalized in FORBIDDEN_AI_ACTIONS:
        raise AIGuardrailViolation(f"AI action is forbidden: {normalized}")
    if normalized in {"approve", "issue", "receive"}:
        raise AIGuardrailViolation(f"AI action is forbidden: {normalized}")


def validate_recommendation_output_shape(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AIGuardrailViolation("AI recommendation output must be an object.")

    missing = sorted(REQUIRED_RECOMMENDATION_OUTPUT_FIELDS - set(data))
    if missing:
        raise AIGuardrailViolation(f"AI recommendation output is missing fields: {', '.join(missing)}")

    confidence = data.get("confidence")
    if not isinstance(confidence, int | float) or confidence < 0 or confidence > 1:
        raise AIGuardrailViolation("AI recommendation confidence must be a number between 0 and 1.")

    if not isinstance(data.get("risk_flags"), list):
        raise AIGuardrailViolation("AI recommendation risk_flags must be a list.")
    if not isinstance(data.get("missing_data_warnings"), list):
        raise AIGuardrailViolation("AI recommendation missing_data_warnings must be a list.")
    if not isinstance(data.get("cited_fields"), list):
        raise AIGuardrailViolation("AI recommendation cited_fields must be a list.")

    sanitized = dict(data)
    sanitized["explanation"] = sanitize_ai_explanation(data.get("explanation"))
    return sanitized


def sanitize_ai_explanation(text: Any) -> str:
    if not isinstance(text, str):
        return ""

    cleaned = " ".join(text.replace("\x00", " ").split())
    if len(cleaned) > MAX_EXPLANATION_LENGTH:
        return cleaned[:MAX_EXPLANATION_LENGTH].rstrip()
    return cleaned
