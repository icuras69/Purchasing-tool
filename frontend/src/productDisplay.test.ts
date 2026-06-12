import { describe, expect, it } from "vitest";
import { isProductMapped, supplierDisplayName } from "./productDisplay";
import type { Product } from "./types";

function product(overrides: Partial<Product>): Product {
  return {
    id: 1,
    name: "Test Product",
    supplier: null,
    supplier_id: null,
    supplier_name: null,
    supplier_code: null,
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
  it("uses OrderPro product supplier before legacy mapping fields", () => {
    expect(
      supplierDisplayName(
        product({
          supplier_id: 12,
          supplier_name: "OrderPro Supplier",
          supplier_code: "OPS",
          mapping_status: "mapped",
          preferred_supplier: "Legacy Preferred",
        }),
      ),
    ).toBe("OrderPro Supplier");
  });

  it("uses preferred_supplier when direct supplier name is absent", () => {
    expect(
      supplierDisplayName(
        product({
          preferred_supplier: "Preferred Supplier",
        }),
      ),
    ).toBe("Preferred Supplier");
  });

  it("uses legacy supplier before legacy supplier mappings", () => {
    expect(
      supplierDisplayName(
        product({
          supplier: { name: "Legacy Product Supplier" },
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
              is_preferred: true,
              match_status: "matched",
              match_method: "exact_sku",
              match_confidence: null,
              last_synced_at: null,
            },
          ],
        }),
      ),
    ).toBe("Legacy Product Supplier (legacy)");
  });

  it("falls back to the preferred legacy supplier mapping", () => {
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
            {
              id: 11,
              supplier_id: 3,
              supplier_name: "Preferred Mapped Supplier",
              supplier_sku: "SKU-2",
              supplier_product_name: "Preferred Mapped Product",
              purchase_price: null,
              currency: null,
              minimum_order_quantity: null,
              pack_size: null,
              lead_time_days: null,
              is_preferred: true,
              match_status: "matched",
              match_method: "exact_sku",
              match_confidence: null,
              last_synced_at: null,
            },
          ],
        }),
      ),
    ).toBe("Preferred Mapped Supplier");
  });

  it("uses legacy supplier fallback", () => {
    expect(supplierDisplayName(product({ supplier: "Legacy Supplier" }))).toBe(
      "Legacy Supplier (legacy)",
    );
  });

  it("shows No supplier assigned when no supplier data exists", () => {
    expect(supplierDisplayName(product({}))).toBe("No supplier assigned");
  });

  it("treats direct supplier fields as mapped even when legacy mappings are empty", () => {
    expect(
      isProductMapped(
        product({
          supplier_id: 10,
          supplier_name: "Direct Supplier",
          supplier_count: 0,
          supplier_mappings: [],
          mapping_status: "unmapped",
        }),
      ),
    ).toBe(true);
  });

  it("treats preferred supplier id and mapped status as mapped fallback signals", () => {
    expect(isProductMapped(product({ preferred_supplier_id: 44 }))).toBe(true);
    expect(isProductMapped(product({ mapping_status: "mapped" }))).toBe(true);
  });

  it("treats products without direct or fallback supplier signals as unmapped", () => {
    expect(isProductMapped(product({}))).toBe(false);
  });
});
