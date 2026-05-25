# Database Review Notes

This is a purchasing AI tool.

Known concern:
- The products table does not directly include supplier information.
- Supplier relationships may exist through a separate mapping table.
- I want to know whether this design is correct or whether products should have fields like default_supplier_id or preferred_supplier_id.

Main business goals:
- Match internal products to supplier products.
- Store supplier-specific SKUs and prices.
- Compare suppliers by price, lead time, MOQ, and availability.
- Generate purchase order recommendations.
- Keep supplier-product relationships clean.
- Avoid duplicating supplier data incorrectly inside the products table.

Please review whether the current schema supports:
- Multiple suppliers per product
- Preferred supplier per product
- Supplier-specific product names
- Supplier SKU/item code
- Purchase price
- Currency
- Lead time
- Minimum order quantity
- Pack size
- Last synced date
- Reorder rules
- Purchase order generation