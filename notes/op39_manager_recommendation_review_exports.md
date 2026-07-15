# OP-39 Manager Recommendation Review Reports and Exports

## Purpose

OP-39 adds read-only manager-facing reports and CSV exports for recommendation review. These reports sit before any purchase order creation and help review stale-demand decisions, manager-approved stale candidates, pending recommendations, and cleanup issues.

## Endpoints Added

- `GET /recommendations/review-summary`
- `GET /recommendations/review-summary/export.csv`
- `GET /recommendations/stale-demand-review/export.csv`
- `GET /recommendations/manager-approved-stale-queue/export.csv`
- `GET /recommendations/cleanup-candidates/export.csv`

## CSV Exports

Stale-demand review export includes product, supplier, last demand, days stale, demand rows, monthly average demand, current stock, lead time, advisory quantity, estimated cost, suggested action, review decision, reviewer, and notes.

Manager-approved stale queue export includes product, supplier, lead time, stock, last demand, advisory quantity, estimated cost, reviewer, review timestamp, notes, safety status, safety blockers, warnings, and suggested next action.

Cleanup candidates export includes recommendation ID, product, supplier, status, quantity, issues, suggested action, purchase readiness, blockers, and warnings.

Review summary export returns `Metric,Value` rows for summary counts and nested count groups.

All CSV files use UTF-8 with BOM and formula-safe text escaping.

## Manager Workflow

1. Review stale-demand candidates.
2. Record manager decisions.
3. Use the manager-approved stale queue to verify safety status.
4. Export reports for offline review.
5. Create only pending review recommendations when intentionally selected.
6. Use the existing PO workflow later.

## Safety

These reports and exports are read-only. They do not call OrderPro, create purchase orders, approve recommendations, convert recommendations to POs, or relax stale-demand policy.

## Recommended OP-40

Add a lightweight manager review dashboard summary in the frontend that surfaces review-summary counts and links directly to the relevant export buttons and review sections.
