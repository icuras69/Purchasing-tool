from typing import Any, Protocol


class LLMProvider(Protocol):
    model_name: str
    prompt_version: str

    def generate_purchase_recommendation_explanation(self, input_data: dict[str, Any]) -> dict[str, Any]:
        ...


class MockLLMProvider:
    model_name = "mock"
    prompt_version = "mock-v1"

    def generate_purchase_recommendation_explanation(self, input_data: dict[str, Any]) -> dict[str, Any]:
        product = input_data.get("product") or {}
        supplier_context = input_data.get("supplier_context_snapshot") or {}
        forecast = input_data.get("forecast_snapshot") or {}
        recommended_quantity = input_data.get("recommended_quantity")

        product_name = product.get("name") or f"product {input_data.get('product_id')}"
        supplier_name = supplier_context.get("supplier_name") or input_data.get("recommended_supplier_name")
        missing_data_warnings: list[str] = []
        risk_flags: list[str] = []

        if not supplier_name:
            missing_data_warnings.append("supplier_name")
        if not supplier_context.get("supplier_sku") and not input_data.get("recommended_supplier_sku"):
            missing_data_warnings.append("supplier_sku")
        if not forecast:
            missing_data_warnings.append("forecast_snapshot")
        if forecast.get("risk_level") in {"high", "critical"}:
            risk_flags.append(f"Forecast risk level is {forecast.get('risk_level')}.")

        action = "reorder" if recommended_quantity and recommended_quantity > 0 else "review"
        summary = f"Review reorder recommendation for {product_name}."
        explanation = (
            f"The recommendation suggests {recommended_quantity or 1:g} units"
            f"{f' from {supplier_name}' if supplier_name else ''} based on stored forecast and supplier mapping data."
        )

        return {
            "suggested_action": action,
            "summary": summary,
            "explanation": explanation,
            "risk_flags": risk_flags,
            "missing_data_warnings": missing_data_warnings,
            "confidence": 0.8 if not missing_data_warnings else 0.45,
            "structured_data_citations": [
                "recommendation.recommended_qty",
                "recommendation.forecast_snapshot",
                "recommendation.supplier_context_snapshot",
            ],
        }


class OpenAIProvider:
    model_name = "openai-disabled"
    prompt_version = "disabled"

    def generate_purchase_recommendation_explanation(self, input_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Real OpenAI LLM calls are disabled for this project stage.")


def get_llm_provider(provider_name: str = "mock", enable_real_llm: bool = False) -> LLMProvider:
    normalized = (provider_name or "mock").strip().lower()
    if normalized == "mock":
        return MockLLMProvider()
    if normalized == "openai":
        if not enable_real_llm:
            raise NotImplementedError("OpenAI provider is configured but real LLM calls are disabled.")
        return OpenAIProvider()
    raise ValueError(f"Unsupported LLM provider: {provider_name}")
