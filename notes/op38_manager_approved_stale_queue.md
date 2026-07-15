# OP-38 Manager-Approved Stale Queue

## Purpose

OP-38 adds a controlled queue for stale-demand products that have already received an explicit local manager decision:

`manager_approved_one_time`

The queue is intended for manual review before creating a normal pending recommendation. It does not approve recommendations, create purchase orders, or change the global stale-demand policy.

## Endpoint Added

`GET /recommendations/manager-approved-stale-queue`

Returns products whose latest stale-demand review decision is `manager_approved_one_time`.

Each row includes product identity, supplier, lead time, stock, last demand date, advisory recommended quantity, estimated cost, reviewer details, safety status, blockers, warnings, and suggested next action.

`POST /recommendations/manager-approved-stale-queue/{product_id}/create-review-recommendation`

Creates or returns a normal `pending_review` reorder recommendation only when the product passes the queue safety checks. It never creates a purchase order and avoids duplicate pending recommendations for the same product.

## Safety Statuses

`ready_for_manual_recommendation`

The product still has a manager-approved stale decision, is inventory, has supplier and lead time, has stale demand, has positive advisory quantity, and the forecast action is `reorder`.

`needs_review`

The product has no hard blocker but has advisory warnings such as missing optional cost, missing optional pack size, fallback MOQ, or returns/negative demand.

`blocked`

The product has a hard blocker such as missing supplier, missing lead time, non-positive quantity, no demand/open demand, non-inventory status, or forecast action is not `reorder`.

## Purchase Order Safety

The create-review endpoint only creates a pending recommendation row. It does not accept the recommendation, convert it to a draft PO, approve anything, issue anything, or call OrderPro.

## Product Impact

- `3020`, `3004`, `3021`, `3121`, `3180`, `3207`: can appear in the queue after `manager_approved_one_time`; only safe rows can create a pending review recommendation.
- `7721`: remains monitor/no reorder and should be blocked unless its forecast becomes a stale reorder candidate.
- `3001`: remains blocked because missing supplier and missing lead time are hard blockers.

## Recommended OP-39

Add manager-facing reporting for approved stale decisions and created review recommendations, including counts by safety status and a simple export for offline review before any PO conversion.
