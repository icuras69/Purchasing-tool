# OP-35 Recommendation Readiness Policy

## Purpose

Recommendation readiness now separates true purchasing blockers from review warnings. Pack size is not currently required by the business for purchasing unless a future policy explicitly requires case, box, or multiple ordering.

## Configuration Defaults

- `RECOMMENDATION_REQUIRE_PACK_SIZE=false`
- `RECOMMENDATION_REQUIRE_COST=false`
- `RECOMMENDATION_ALLOW_STALE_DEMAND=false`

The legacy stale-demand setting remains supported. Stale-only demand is allowed only when either stale-demand allow setting is enabled.

## Hard Blockers

Recommendations are blocked when any of these are present:

- Missing supplier.
- Missing usable lead time.
- No demand history and no open customer demand.
- Non-positive recommended quantity.
- Non-inventory product.
- Forecast action is not reorder.
- Stale-only demand when stale-demand recommendations are not allowed.
- Missing cost when `RECOMMENDATION_REQUIRE_COST=true`.
- Missing pack size when `RECOMMENDATION_REQUIRE_PACK_SIZE=true`.

## Review Warnings

These conditions are surfaced for review but do not necessarily block purchasing:

- Missing pack size when `RECOMMENDATION_REQUIRE_PACK_SIZE=false`.
- Missing cost when `RECOMMENDATION_REQUIRE_COST=false`.
- Fallback MOQ.
- Returns or negative demand.
- Quantity raised to MOQ.
- Quantity rounded to a pack multiple.
- Stale-demand warning text, while stale-only demand remains blocked by default for new recommendations.

## Pack Size

Because every current product lacks effective pack-size data, missing pack size is advisory by default. The recommendation engine does not apply pack multiple rounding when pack size is missing. Cleanup candidates should not be created solely because pack size is missing while pack size is optional.

## Cost

Missing cost is advisory by default. When cost is missing, recommendations can still be generated, but estimated unit and total cost may be blank. If `RECOMMENDATION_REQUIRE_COST=true`, missing cost becomes a hard blocker.

## Stale Demand

Stale-only legacy demand remains conservative. By default, stale-only recommendations require manual review and are blocked from new recommendation creation. This OP relaxes missing pack size only; it does not relax stale-demand policy.

## Existing Recommendations

No existing recommendation rows are mutated automatically. Explainability and cleanup endpoints reinterpret existing rows under the current policy. Existing rows whose only issue is optional missing pack size are no longer treated as cleanup-required.

## Demo Product Impact

- Products `3020`, `3004`, `3021`, `3121`, `3180`, and `3207`: missing pack size alone should no longer block readiness. Any stale-only demand still prevents full order-ready status unless stale demand is explicitly allowed.
- Product `7721`: remains monitor/no reorder when the forecast action is not reorder.
- Product `3001`: remains blocked when missing supplier and lead time are present.

Seasonality remains advisory and does not change recommendation quantities.
