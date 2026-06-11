# Supplier Assignment Review

OrderPro is the source of truth for product and supplier identity, but the current OrderPro product API does not expose supplier assignment for every product. During the transition, some synced OrderPro products can therefore have `products.supplier_id` unset locally.

Missing supplier assignment is blocking for supplier forecasts and draft purchase order generation. This review workflow surfaces deterministic local evidence so a user can confirm the supplier assignment locally without writing back to OrderPro.

## Evidence Sources

Allowed suggestion evidence is intentionally narrow:

- Exact supplier code evidence from an import/export source, when available.
- Mirrored OrderPro purchase order lines linked to the product and supplier.
- Local purchase order lines linked to the product and supplier.
- Legacy `product_suppliers` mappings as low-confidence transitional evidence only.
- Historical supplier code/name evidence only when it maps uniquely to one current supplier.

The workflow does not infer suppliers from product names, descriptions, categories, or fuzzy matching.

Fresh OrderPro product exports can be imported through `scripts/import_orderpro_product_supplier_export.py`.
See `app/docs/orderpro_product_supplier_export.md` for supported columns, matching precedence, and confirmation rules.

## Confidence Rules

- `high`: repeated purchase order evidence from a single supplier, or an exact supplier-code match when provided by a trusted import.
- `medium`: one recent purchase order line from a single supplier.
- `low`: conflicting purchase-order evidence or legacy `ProductSupplier` evidence.
- `none`: no deterministic evidence.

Unconfirmed suggestions never drive forecasts, recommendations, or purchase order generation.

## Local Confirmation

Confirming a supplier assignment:

- updates `products.supplier_id` locally;
- records the decision in `product_supplier_assignment_reviews`;
- does not call OrderPro;
- does not create or edit purchase orders;
- does not change forecast formulas.

Import-based exact-code confirmations use `reviewed_by = "orderpro_product_export"` and remain local-only.

Rejecting a suggestion records the review decision and leaves `products.supplier_id` unchanged.

## CLI Workflow

Dry-run:

```powershell
python scripts/plan_supplier_assignments.py --dry-run --save-report
```

Create or update review records only:

```powershell
python scripts/plan_supplier_assignments.py --apply-suggestions --save-report
```

Confirm strict high-confidence suggestions locally:

```powershell
python scripts/plan_supplier_assignments.py --apply-suggestions --confirm-high-confidence --save-report
```

Do not use the confirmation flag for mass updates until the review report has been checked.

## APIs

- `GET /supplier-assignment-review/summary`
- `GET /supplier-assignment-review/items`
- `GET /products/{product_id}/supplier-assignment-review`
- `POST /products/{product_id}/supplier-assignment-review/confirm`
- `POST /products/{product_id}/supplier-assignment-review/reject`

Confirmed suppliers improve forecast readiness because the product now has the required `supplier_id`. Suggestions alone keep the product blocked and reviewable.

## Future OrderPro Write-Back

Any future write-back to OrderPro should be a separate controlled sync with explicit permissions, audit logging, and a staging read-only comparison first. This workflow is local-only.
