# OP-37 Stale-Demand Manager Decisions

## Storage Model

OP-37 adds a local table:

`stale_demand_review_decisions`

The table stores one latest decision per product:

- `product_id`
- optional `recommendation_id`
- `decision`
- `reviewed_by`
- optional `notes`
- `reviewed_at`
- `created_at`
- `updated_at`

This is local-only and does not write to OrderPro.

## Allowed Decisions

- `watchlist`
- `manager_approved_one_time`
- `rejected_stale`
- `wait_for_recent_demand`

## Endpoints

List decisions:

`GET /recommendations/stale-demand-decisions`

Save a product decision:

`POST /recommendations/stale-demand-review/{product_id}/decision`

Request body:

```json
{
  "decision": "manager_approved_one_time",
  "reviewed_by": "Maged",
  "notes": "Manager approved one-time reorder for review."
}
```

The stale-demand review endpoint now includes:

- `review_decision`
- `reviewed_by`
- `review_notes`
- `reviewed_at`
- `decision_status`

It also supports:

`GET /recommendations/stale-demand-review?decision=unreviewed|manager_approved_one_time|watchlist|rejected_stale|wait_for_recent_demand|all`

## Validation Rules

- Product must exist.
- `decision` must be one of the allowed values.
- `reviewed_by` is required.
- `manager_approved_one_time` and `wait_for_recent_demand` require the product to currently be eligible for stale-demand review.
- `watchlist` and `rejected_stale` may be recorded for an existing product even if it is not currently eligible.
- Saving a decision does not create purchase orders.
- Saving a decision does not change forecast formulas.
- Saving a decision does not globally allow stale demand.

## Recommendation Behavior

Stale-only demand remains blocked by default.

If the latest local decision is `manager_approved_one_time`, the existing explicit manual recommendation creation endpoint may create a pending review recommendation for that product, provided the normal hard requirements still pass:

- supplier exists;
- lead time exists;
- product is inventory;
- forecast action is reorder;
- advisory quantity is positive.

This does not approve or issue a PO. It only allows a manually requested recommendation into the existing review flow.

## PO Safety

No purchase order is created by the manager decision endpoint.

Existing conversion rules remain unchanged. A purchase order still requires explicit downstream user action through the existing recommendation and PO workflow.

## Product Impact

- `3020`: stale-demand candidate; can receive `manager_approved_one_time`, then explicit manual recommendation creation can proceed to pending review.
- `3004`: stale-demand candidate; same decision behavior as `3020`.
- `3021`: stale-demand candidate; same decision behavior as `3020`.
- `3121`: stale-demand candidate; same decision behavior as `3020`.
- `3180`: stale-demand candidate; same decision behavior as `3020`.
- `3207`: stale-demand candidate; same decision behavior as `3020`.
- `7721`: monitor/no reorder; cannot be manager-approved as a stale reorder candidate.
- `3001`: blocked by missing supplier and lead time; cannot be manager-approved as a stale reorder candidate until those hard blockers are resolved.

## Migration

Apply before using the new workflow on a persistent database:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Notes

OP-37 does not delete existing recommendation rows, does not mutate recommendations automatically, does not call OrderPro, and does not relax stale-demand policy globally.
