# OP-40 Manager Review Dashboard

## UI Section Added

The Recommendations page now includes a compact `Manager Review Summary` section above the recommendation creation workflow.

## Summary Fields Displayed

- Total recommendations
- Pending review recommendations
- Accepted recommendations
- Rejected recommendations
- Stale-demand candidates
- Manager-approved stale queue count
- Cleanup candidates
- Ready for manual review
- Blocked or unsafe

## Export Buttons Added

- Review Summary CSV
- Stale Demand Review CSV
- Manager-Approved Queue CSV
- Cleanup Candidates CSV

The buttons use the OP-39 export endpoints and existing frontend CSV download behavior.

## Manager Use

The summary gives a quick first-pass answer to what needs attention before any PO work:

1. Review cleanup candidates before PO conversion.
2. Review manager-approved stale candidates before creating pending recommendations.
3. Review stale-demand candidates and record manager decisions.
4. Export reports for offline review when needed.

## Safety

The dashboard is read-only. It does not call OrderPro, create purchase orders, approve recommendations, mutate recommendation status, or relax stale-demand policy.

## Recommended OP-41

Add lightweight filters to the manager-approved stale queue so managers can focus on `ready_for_manual_recommendation`, `needs_review`, or `blocked` items without exporting first.
