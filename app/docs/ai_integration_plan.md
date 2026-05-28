# AI Integration Plan

## Purpose

Future LLM support should make purchasing recommendations easier to understand, not replace the structured purchasing workflow. The LLM may help users interpret forecast, inventory, and supplier mapping data, but it must not become the system of record or an approval authority.

## Intended LLM Uses

- Explain purchase recommendations in plain language.
- Compare supplier options using existing `ProductSupplier` records.
- Summarize reorder risk and missing data.
- Generate human-readable recommendation notes.
- Help users understand why a draft purchase order was suggested.

## Required Inputs

Every AI recommendation flow should be grounded in structured backend data:

- Product identity and product metadata.
- Current stock or synced inventory position.
- Forecast response and reorder recommendation.
- `supplier_context` from forecasting.
- Confirmed `ProductSupplier` mapping data.
- Purchase history, once available.
- Open purchase orders, once available.

## Required Structured Output

LLM output must be parsed into structured fields before it can affect application state:

- Recommendation summary.
- Risk flags.
- Confidence.
- Suggested action.
- Explanation.
- Missing data warnings.
- Cited structured data fields used to reach the recommendation.

## Audit Requirements

Any future LLM-generated recommendation must preserve:

- Model name.
- Prompt version.
- Input snapshot.
- Output snapshot.
- Created timestamp.
- Reviewer identity.
- Review decision.
- Converted purchase order ID if converted.

## Human Approval Rule

LLM recommendations are advisory only. LLM output may create or update recommendation records only through controlled backend services. LLM output may only lead to draft purchase order creation, never purchase order approval, issuing, receiving, inventory mutation, or external supplier ordering.

## Current Implementation State

The current backend LLM layer uses `MockLLMProvider` only. It is deterministic, performs no network calls, requires no API key, and is suitable for tests and local development. Real OpenAI integration is intentionally disabled until a later task adds structured output calls, provider configuration, observability, and production key handling.

The mock service can generate explanation text for an existing recommendation and update only safe explanation-related fields:

- `reason`
- `explanation`
- `confidence`
- `model_name`
- `prompt_version`

It does not change recommendation status, create purchase orders, approve purchase orders, issue purchase orders, update inventory, or modify supplier/product mappings.

## Next Real-Provider Step

The next LLM task should add a real provider behind explicit configuration, use structured outputs, store an output snapshot if a dedicated field exists, and keep the same guardrail contract. The LLM remains advisory text only; human review and the existing draft PO workflow stay mandatory.
