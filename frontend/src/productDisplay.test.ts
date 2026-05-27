import { describe, expect, it } from "vitest";
import { supplierDisplayName } from "./productDisplay";
import type { Product } from "./types";

function product(overrides: Partial<Product>): Product {
  return {
    id: 1,
    name: "Test Product",
    supplier: null,
    current_stock: 0,
    supplier_count: 0,
    preferred_supplier: null,
    preferred_supplier_id: null,
    preferred_supplier_sku: null,
    supplier_mappings: [],
    mapping_status: "unmapped",
    ...overrides,
  };
}

describe("supplierDisplayName", () => {
  it("uses preferred_supplier for mapped products", () => {
    expect(
      supplierDisplayName(
        product({
          mapping_status: "mapped",
          preferred_supplier: "Preferred Supplier",
        }),
      ),
    ).toBe("Preferred Supplier");
  });

  it("falls back to the first supplier mapping", () => {
    expect(
      supplierDisplayName(
        product({
          mapping_status: "mapped",
          supplier_mappings: [
            {
              id: 10,
              supplier_id: 2,
              supplier_name: "Mapped Supplier",
              supplier_sku: "SKU-1",
              supplier_product_name: "Mapped Product",
              purchase_price: null,
              currency: null,
              minimum_order_quantity: null,
              pack_size: null,
              lead_time_days: null,
              is_preferred: false,
              match_status: "matched",
              match_method: "exact_sku",
              match_confidence: null,
              last_synced_at: null,
            },
          ],
        }),
      ),
    ).toBe("Mapped Supplier");
  });

  it("uses legacy supplier fallback", () => {
    expect(supplierDisplayName(product({ supplier: "Legacy Supplier" }))).toBe(
      "Legacy Supplier (legacy)",
    );
  });

  it("shows Unmapped when no supplier data exists", () => {
    expect(supplierDisplayName(product({}))).toBe("Unmapped");
  });
});
