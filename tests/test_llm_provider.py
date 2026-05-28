import pytest

from app.services.llm_provider import MockLLMProvider, OpenAIProvider, get_llm_provider


def test_mock_llm_provider_returns_deterministic_structured_output():
    provider = MockLLMProvider()
    input_data = {
        "product_id": 10,
        "product": {"id": 10, "name": "Widget"},
        "recommended_quantity": 8,
        "recommended_supplier_name": "Acme Supply",
        "recommended_supplier_sku": "ACME-1",
        "forecast_snapshot": {"risk_level": "low"},
        "supplier_context_snapshot": {
            "supplier_name": "Acme Supply",
            "supplier_sku": "ACME-1",
        },
    }

    first = provider.generate_purchase_recommendation_explanation(input_data)
    second = provider.generate_purchase_recommendation_explanation(input_data)

    assert first == second
    assert first["suggested_action"] == "reorder"
    assert first["summary"] == "Review reorder recommendation for Widget."
    assert first["confidence"] == 0.8
    assert first["structured_data_citations"] == [
        "recommendation.recommended_qty",
        "recommendation.forecast_snapshot",
        "recommendation.supplier_context_snapshot",
    ]


def test_mock_llm_provider_marks_missing_data_as_lower_confidence():
    provider = MockLLMProvider()

    output = provider.generate_purchase_recommendation_explanation(
        {
            "product_id": 10,
            "recommended_quantity": 1,
            "forecast_snapshot": {},
            "supplier_context_snapshot": {},
        }
    )

    assert output["confidence"] == 0.45
    assert "supplier_name" in output["missing_data_warnings"]
    assert "supplier_sku" in output["missing_data_warnings"]
    assert "forecast_snapshot" in output["missing_data_warnings"]


def test_openai_provider_is_disabled_and_does_not_call_external_services():
    provider = OpenAIProvider()

    with pytest.raises(NotImplementedError):
        provider.generate_purchase_recommendation_explanation({})


def test_get_llm_provider_rejects_disabled_openai_provider():
    with pytest.raises(NotImplementedError):
        get_llm_provider("openai", enable_real_llm=False)


def test_get_llm_provider_defaults_to_mock():
    provider = get_llm_provider()

    assert isinstance(provider, MockLLMProvider)
