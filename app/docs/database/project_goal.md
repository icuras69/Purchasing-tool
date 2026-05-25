@"
# Purchasing AI Tool - Project Goal

This project is a purchasing AI tool.

The goal of the app is not only to display suppliers or products, but to support the full purchasing workflow.

The app should eventually help with:

1. Managing products
2. Managing suppliers
3. Mapping internal products to supplier products
4. Handling supplier-specific SKUs, names, prices, pack sizes, and minimum order quantities
5. Comparing suppliers by price, lead time, availability, and reliability
6. Detecting missing or weak product-supplier mappings
7. Suggesting what products need to be reordered
8. Generating purchase order recommendations
9. Explaining why a purchase recommendation was made
10. Keeping human approval before any final purchasing action

Important design expectations:

- A product may have more than one supplier.
- Supplier information should not be duplicated carelessly inside the products table.
- Product-supplier mapping should support supplier SKU, supplier product name, purchase price, currency, MOQ, pack size, lead time, and preferred supplier logic.
- The app should avoid hardcoded assumptions that each product has only one supplier.
- The backend, frontend, database schema, and API design should support future AI purchasing recommendations.
- The system should be maintainable, testable, and safe before adding AI automation.

Review goal:

Codex should inspect the whole project and identify logical, architectural, database, backend, API, frontend, and workflow issues that may prevent the app from becoming a reliable purchasing AI tool.

Codex should not only fix the current supplier display issue. It should review the full design.
"@ | Out-File -Encoding utf8 app\docs\project_goal.md