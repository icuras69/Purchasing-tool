# OP-36 Stale-Demand Review Workflow

## Policy

Stale-only legacy demand remains conservative. Products with old sales history, no recent demand, and a positive advisory reorder quantity are not treated as normal order-ready recommendations. They require manager review before any purchase order decision.

Missing pack size remains advisory under OP-35. OP-36 does not relax stale-demand policy globally and does not change forecast quantities.

## Endpoint

`GET /recommendations/stale-demand-review`

The endpoint is read-only. It returns products where:

- Demand exists and is stale-only.
- Supplier and usable lead time are present.
- Product is inventory.
- Forecast action is reorder.
- Advisory recommended quantity is positive.
- The main hard blocker is stale-demand review.

Returned fields include product identity, supplier, last demand date, days since last demand, demand rows, monthly average demand, current stock, lead time, advisory quantity, estimated cost when available, blockers, warnings, readiness issues, and suggested action.

## Suggested Actions

- `approve_one_time_reorder`: candidate has zero/negative current stock and a positive advisory quantity, but still requires explicit manager review.
- `manual_review`: candidate needs business judgment before any PO action.
- Other manager decisions remain available outside this read-only endpoint: watchlist, reject stale recommendation, wait for recent demand, or request manager confirmation.

## Mutation Endpoints

No mutation endpoints were added in OP-36. This avoids introducing one-off approval status semantics or automatic recommendation updates. Existing accept/reject/convert flows remain unchanged, and converting still only creates draft purchase orders when explicitly invoked through existing workflows.

## Cleanup Candidates

Existing stale-only actionable recommendation rows are grouped under:

`stale_demand_review_required`

Their suggested cleanup action is:

`review_stale_demand`

No existing recommendation rows are automatically rejected, updated, or converted.

## Current Local Candidate Count

Read-only local verification with `limit=2000` found:

- `319` stale-demand review candidates.
- Suggested actions: `approve_one_time_reorder=292`, `manual_review=27`.

## Demo Product Impact

- `3020`: included in stale-demand review; supplier Christies; lead time 3; advisory quantity 6.
- `3004`: included in stale-demand review; supplier Acravet Ltd; lead time 2; advisory quantity 2.
- `3021`: included in stale-demand review; supplier Christies; lead time 3; advisory quantity 1.
- `3121`: included in stale-demand review; supplier Mullinahone; lead time 7; advisory quantity 7.
- `3180`: included in stale-demand review; supplier Cleanline; lead time 2; advisory quantity 1.
- `3207`: included in stale-demand review; supplier Osmonds; lead time 21; advisory quantity 1.
- `7721`: excluded; monitor/no reorder with zero recommendation quantity.
- `3001`: excluded; missing supplier and lead time are hard blockers.

## Recommended Manager Decision Flow

1. Review stale-demand candidates sorted by advisory quantity and stock position.
2. Confirm whether the product is still commercially relevant.
3. If the product should be stocked again, create or approve a one-time recommendation manually through the normal review flow.
4. If the product should not be reordered, reject or watchlist the stale recommendation.
5. If unsure, wait for recent demand or request manager confirmation.

Seasonality remains advisory and purchase orders are never created automatically.
