# AI Guardrails

## Non-Negotiable Boundaries

The LLM must not:

- Approve purchase orders.
- Issue purchase orders.
- Receive purchase orders.
- Directly modify supplier mappings.
- Directly modify product records.
- Directly modify inventory.
- Bypass human approval.
- Create external supplier orders.
- Make purchasing decisions without structured data.

## Allowed AI Actions

Allowed AI actions are advisory or draft-only:

- `explain_recommendation`
- `compare_suppliers`
- `suggest_reorder`
- `summarize_risk`
- `create_recommendation_draft`

## Forbidden AI Actions

Forbidden AI actions must be rejected by backend guardrails:

- `approve_purchase_order`
- `issue_purchase_order`
- `receive_purchase_order`
- `delete_mapping`
- `update_inventory`
- `place_external_order`
- `bypass_approval`

## Recommendation Safety

AI output must flow through recommendation review. A recommendation can be accepted or rejected by a user. A recommendation can be converted only into a draft purchase order. It must never be converted directly into an approved, issued, received, or externally submitted purchase order.

## Data Integrity

AI output must not directly update database models. The backend should validate action intent, required output shape, and explanation text before storing any AI-assisted recommendation.
