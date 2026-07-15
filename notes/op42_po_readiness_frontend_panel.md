# OP-42 Frontend PO Readiness Panel

## UI panel added

The Recommendations detail view now includes a compact `PO Readiness` panel. It loads whenever a recommendation is selected or refreshed.

The panel shows:

- Ready/not-ready state.
- Product ID and product name.
- Supplier name.
- Supplier source.
- Canonical supplier check result.
- Recommended quantity.
- Estimated unit cost.
- Estimated total cost.
- Required manager decision for stale-only recommendations.
- Hard blockers.
- Advisory warnings.

## API helper added

Added frontend API helper:

```text
getRecommendationPOReadiness(recommendationId)
```

It calls:

```text
GET /recommendations/{recommendation_id}/po-readiness
```

## Conversion gating

The `Convert to Draft PO` button now waits for PO readiness to load. If the backend readiness response returns:

```text
can_create_draft_po = false
```

the button is disabled and blockers are displayed in the readiness panel.

If readiness cannot be loaded, the page shows a non-blocking warning and leaves backend validation as the final authority. The backend conversion endpoint still performs all canonical supplier and safety checks.

## Loading and error behavior

- While readiness is loading, the panel shows `Loading PO readiness...`.
- If readiness fails, the panel shows the error without breaking the rest of the Recommendation details page.
- Backend conversion errors remain visible through the existing recommendation action error path.

## Safety behavior

The frontend does not approve, issue, or create purchase orders automatically. It only lets users explicitly convert a recommendation, and the backend remains the final authority.

## Tests run

Frontend tests and build should be run with:

```powershell
cd "D:\Projects\purchasing-ai\frontend"
Remove-Item Env:VITE_AUTH_ENABLED -ErrorAction SilentlyContinue
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm.cmd run test -- --run
npm.cmd run build
```

## Recommended OP-43

Add a purchase-order review preflight on the PO detail page before submit/approval so draft POs clearly show any missing cost, missing supplier snapshot, stale-demand origin, or incomplete line data before manager approval.
