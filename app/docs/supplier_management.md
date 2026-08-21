# Supplier management

The **Suppliers** tab is the local source for supplier purchasing details that are not managed in
OrderPro. Supplier identity fields remain read-only, while contact details, payment terms, lead
times, and notes can be edited in Purchasing AI.

## Data ownership

- OrderPro continues to supply the supplier ID, code, name, active status, and sync timestamp.
- Purchasing AI owns website, preferred contact method, payment terms, lead-time values, and notes.
- Email and phone are initially imported from OrderPro. After the supplier profile is edited in
  Purchasing AI, local email and phone overrides are preserved by later OrderPro syncs.
- `PATCH /suppliers/{supplier_id}` only writes to the local database. It never calls OrderPro.

## Forecast behavior

If a product has no positive product-level lead time, forecasting falls back to the linked
supplier's `lead_time_days`. Updating a supplier lead time therefore affects every linked product
that does not already have its own lead time.

For ED&F Man (local supplier ID 18), saving a lead time of 10 days gives both linked molasses
products a usable supplier-level lead time. Missing pack sizes remain a separate forecast-readiness
warning and must be reviewed per product.

## Deployment

Run `alembic upgrade head` after pulling this change. The migration adds the
`suppliers.local_profile_override` flag used to protect locally maintained contact details from
later OrderPro imports.
