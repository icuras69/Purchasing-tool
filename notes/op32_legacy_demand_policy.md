# OP-32 Legacy Demand Policy, Returns Handling, and Stale-Demand Safety

## Goal

Make legacy `usage_history` demand safer before recommendations are trusted for purchasing. OP-32 keeps the OP-31 explain and audit endpoints, adds a read-only demand policy impact endpoint, uses net legacy demand by default, and prevents stale-only legacy demand from becoming a normal new actionable recommendation.

## Current legacy demand behavior found

Before OP-32, `app/services/forecasting.py` used `calculate_usage_history_demand()` as the OrderPro fallback demand source. It queried all `UsageHistory` rows for a product, ordered by `usage_date`, and summed `qty_used` across the full available history with no lookback cutoff. `qty_returned` and `net_qty` existed on imported demand rows, but the legacy forecast formula did not use them.

`app/services/demand_history_reconciliation.py` imports legacy demand rows with `qty_used`, `qty_returned`, and `net_qty`, preserving return/negative-row signals. Other reconciliation and seasonality paths already referenced `net_qty`, but the recommendation forecast fallback did not.

OP-31 explainability warned about stale demand and return/negative-row evidence, but it did not change forecast quantity selection or stale-only recommendation behavior. Stale-only products could still produce normal actionable recommendations when supplier, lead time, and stock conditions were otherwise usable.

Monthly average demand in recommendation explanations is derived from forecast average daily usage as:

```text
monthly_average_demand = average_daily_usage * 30.4375
```

## Policy implemented

Default legacy demand quantity mode is now configurable and conservative:

```text
LEGACY_DEMAND_QUANTITY_MODE=net_qty
LEGACY_DEMAND_STALE_DAYS=180
LEGACY_DEMAND_LOOKBACK_DAYS=null/all
ALLOW_STALE_DEMAND_RECOMMENDATIONS=false
```

When `LEGACY_DEMAND_QUANTITY_MODE=net_qty`, legacy demand uses `UsageHistory.net_qty` when present and falls back to `qty_used` only when `net_qty` is missing. Total legacy demand is clamped at zero so negative net demand cannot create a reorder recommendation.

The default lookback remains all history to avoid a broad formula shift in this OP. The new policy impact endpoint can compare 90, 180, 365, and all-history windows without writing data.

Stale-only legacy demand is no longer treated as normal actionable demand by default. If a product has positive advisory reorder math but its only demand signal is stale legacy demand, the explain endpoint returns `status="needs_review"`, `readiness_status="partially_ready"`, and `stale_demand_policy="manual_review_required"`. New recommendation creation blocks this case unless `ALLOW_STALE_DEMAND_RECOMMENDATIONS=true`.

Existing recommendation rows are not deleted or modified. The audit path flags existing stale-only actionable rows for human review.

## Files inspected

- `app/services/forecasting.py`
- `app/services/recommendation_audit.py`
- `app/services/recommendations.py`
- `app/services/demand_history_reconciliation.py`
- `app/models/usage_history.py`
- `app/routes/recommendations.py`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `tests/test_recommendations.py`
- `tests/test_forecasting_supplier_resolution.py`
- `tests/test_forecast_response_supplier_context.py`
- `tests/test_direct_supplier_repair.py`

## Files changed

- `app/core/config.py`
- `app/routes/recommendations.py`
- `app/services/forecasting.py`
- `app/services/orderpro_demand.py`
- `app/services/recommendation_audit.py`
- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `tests/test_recommendations.py`
- `tests/test_direct_supplier_repair.py`
- `notes/op32_legacy_demand_policy.md`

## Read-only demand policy impact endpoint

Added:

```text
GET /recommendations/demand-policy-impact
```

Supported query params:

```text
lookback_days=90|180|365|all
quantity_mode=qty_used|net_qty
stale_days=180
limit=500
```

The endpoint is read-only. It evaluates forecast/explain behavior under current settings, net quantity policy, a requested policy, and a recent-window policy. It reports actionable counts, stale-only counts, quantity/status changes, and examples of changed products.

## Recommendation explanation fields added

Recommendation explanations and forecast snapshots now include:

- `demand_quantity_mode`
- `legacy_demand_quantity_mode`
- `legacy_demand_raw_units_in_window`
- `legacy_demand_negative_or_return_rows`
- `legacy_demand_stale_days`
- `demand_policy_status`
- `stale_demand_only`
- `stale_demand_policy`

The frontend recommendation details panel now shows demand quantity mode, demand policy, last demand date, stale-demand-only status, and return/negative-row count when those fields are present.

## Impact summary from read-only local verification

Verification used the local database in read-only service calls. No OrderPro calls were made and no database rows were written.

```text
Products evaluated: 5,197
Actionable recommendations under current policy: 94
Actionable recommendations using net_qty: 94
Actionable recommendations using recent-window policy: 94
Stale-only actionable count under new policy: 0
Stale-only needs-review count under new policy: 480
Products where recommendation quantity changes: 480
Products where recommendation status changes: 491
Existing recommendation rows evaluated by audit: 9
Existing suspicious recommendation rows: 7
Existing stale-only actionable recommendation rows flagged: 5
```

## Manual/API verification products

| Product ID | Status | Supplier | Last demand date | Demand mode | Stale-only | Recommended qty | Notes |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| 3020 | needs_review | Christies | 2025-06-03 | net_qty | true | 6.0 | Advisory reorder remains visible, but stale-only demand requires manual review. |
| 3004 | needs_review | Acravet Ltd | 2025-07-02 | net_qty | true | 2.0 | Stale-only legacy demand; missing pack size warning remains. |
| 3021 | needs_review | Christies | 2025-11-03 | net_qty | true | 1.0 | Stale-only legacy demand; advisory quantity only. |
| 3121 | needs_review | Mullinahone | 2024-03-19 | net_qty | true | 7.0 | Stale-only legacy demand; advisory quantity only. |
| 3180 | needs_review | Cleanline | 2025-01-29 | net_qty | true | 1.0 | Stale-only legacy demand; advisory quantity only. |
| 3207 | needs_review | Osmonds | 2025-10-03 | net_qty | true | 1.0 | Stale-only legacy demand; advisory quantity only. |
| 7721 | monitor | Mullinahone | 2026-06-04 | n/a | false | 0.0 | Recent non-legacy demand signal; sufficient cover, so no reorder. |
| 3001 | blocked | None | 2024-12-20 | net_qty | true | 0.0 | Missing supplier and lead time remain hard blockers. |

Example explanation for Product ID 3020:

```json
{
  "product_id": 3020,
  "status": "needs_review",
  "readiness_status": "partially_ready",
  "supplier_name": "Christies",
  "last_demand_date": "2025-06-03",
  "demand_quantity_mode": "net_qty",
  "stale_demand_only": true,
  "stale_demand_policy": "manual_review_required",
  "monthly_average_demand": 60.88,
  "recommended_quantity": 6.0,
  "warnings": [
    "Stale demand only; last demand is older than 180 days",
    "Missing pack size"
  ],
  "blockers": []
}
```

Example blocked product:

```json
{
  "product_id": 3001,
  "status": "blocked",
  "readiness_status": "blocked",
  "supplier_name": null,
  "last_demand_date": "2024-12-20",
  "demand_quantity_mode": "net_qty",
  "stale_demand_only": true,
  "stale_demand_policy": "manual_review_required",
  "recommended_quantity": 0.0,
  "blockers": [
    "Missing supplier",
    "Missing lead time"
  ]
}
```

## Tests added or updated

Backend tests now cover:

- Returns reduce legacy demand through `net_qty`.
- Missing `net_qty` falls back to `qty_used`.
- Negative net legacy demand does not create actionable reorder.
- Recent demand can still produce actionable reorder when supplier, lead time, and stock conditions are valid.
- Stale-only legacy demand becomes `needs_review` while preserving advisory projected demand and quantity.
- New recommendation creation blocks stale-only legacy demand by default.
- The demand policy impact endpoint reports stale and recent policy changes.
- Recommendation explanations expose the selected demand quantity mode and stale-demand policy.

Frontend tests now cover the added recommendation detail fields.

## Validation

Backend:

```text
472 passed, 718 warnings
```

Frontend:

```text
140 passed
npm run build completed successfully
```

Warnings are existing deprecation and test-environment warnings, primarily around `datetime.utcnow()` and pydantic validator style.

## Constraints confirmed

- No OrderPro calls were added or run.
- No Render config was changed.
- No database data was changed.
- No purchase orders were created automatically.
- OP-31 explain and audit endpoints remain in place.

## Remaining risks

- `LEGACY_DEMAND_LOOKBACK_DAYS` defaults to all history for minimal breakage. The impact endpoint shows 480 products now require review because their only demand signal is stale legacy demand, but the baseline average still uses all legacy history unless configured otherwise.
- Existing stale-only actionable recommendation rows are flagged, not modified. A future cleanup or review workflow should decide whether to migrate, close, or annotate those rows.
- Missing pack size remains common, so some advisory quantities still lack pack-multiple rounding.

## Recommended OP-33

Focus OP-33 on purchase-quality guardrails around pack size, MOQ, and existing recommendation cleanup:

- Review products with missing pack size but nonzero advisory reorder quantities.
- Decide whether existing stale-only actionable recommendation rows should be migrated to review status.
- Add a manager-facing watchlist for stale-demand needs-review products.
- Compare all-history vs 365-day legacy demand as a deliberate policy change after stakeholder review.
