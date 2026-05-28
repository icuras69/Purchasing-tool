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
