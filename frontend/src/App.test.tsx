import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
} from "./api";
import type { Product, ProductSupplierMapping, WeakMapping } from "./types";

vi.mock("./api", () => ({
  fetchProducts: vi.fn(),
  fetchUnmappedProducts: vi.fn(),
  fetchWeakMappings: vi.fn(),
  fetchProductSuppliers: vi.fn(),
}));

const productDefaults: Product = {
  id: 1,
  name: "Mapped Product",
  supplier: null,
  current_stock: 12,
  supplier_count: 1,
  preferred_supplier: "Acme Supplies",
  preferred_supplier_id: 10,
  preferred_supplier_sku: "ACME-1",
  supplier_mappings: [],
  mapping_status: "mapped",
};

const supplierMappingDefaults: ProductSupplierMapping = {
  id: 100,
  product_id: 1,
  product_name: "Mapped Product",
  supplier_id: 10,
  supplier_name: "Acme Supplies",
  supplier_sku: "ACME-1",
  supplier_product_name: "Acme Product Pack",
  purchase_price: 9.5,
  currency: "USD",
  minimum_order_quantity: null,
  pack_size: null,
  lead_time_days: null,
  is_preferred: true,
  match_status: "matched",
  match_method: "sku",
  match_confidence: null,
  last_synced_at: null,
};

function mockProduct(overrides: Partial<Product> = {}): Product {
  return {
    ...productDefaults,
    ...overrides,
  };
}

function mockSupplierMapping(
  overrides: Partial<ProductSupplierMapping> = {},
): ProductSupplierMapping {
  return {
    ...supplierMappingDefaults,
    ...overrides,
  };
}

function mockWeakMapping(overrides: Partial<WeakMapping> = {}): WeakMapping {
  return {
    product_id: 2,
    product_name: "Questionable Product",
    reason: "Low confidence",
    mapping_id: 200,
    supplier_id: 20,
    supplier_name: "Maybe Supplier",
    supplier_sku: "MAYBE-2",
    supplier_product_name: "Maybe Product",
    match_status: "review",
    match_method: "fuzzy",
    match_confidence: 0.4,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(fetchProducts).mockResolvedValue([]);
  vi.mocked(fetchUnmappedProducts).mockResolvedValue([]);
  vi.mocked(fetchWeakMappings).mockResolvedValue([]);
  vi.mocked(fetchProductSuppliers).mockResolvedValue([]);
});

describe("App mapping review workflow", () => {
  it("renders navigation tabs", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unmapped Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weak Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Mappings" })).toBeInTheDocument();
    expect(await screen.findByText("No products found.")).toBeInTheDocument();
  });

  it("shows unmapped products with a clear review status", async () => {
    vi.mocked(fetchUnmappedProducts).mockResolvedValue([
      mockProduct({
        id: 2,
        name: "Unmapped Product",
        current_stock: 3,
        supplier_count: 0,
        preferred_supplier: null,
        preferred_supplier_id: null,
        preferred_supplier_sku: null,
        mapping_status: "unmapped",
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));

    expect(await screen.findByText("Unmapped Product")).toBeInTheDocument();
    expect(screen.getByText("Needs supplier mapping")).toBeInTheDocument();
    expect(screen.getByText("unmapped")).toBeInTheDocument();
  });

  it("shows supplier mapping product and supplier fields", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));

    expect(await screen.findByText("Mapped Product")).toBeInTheDocument();
    expect(screen.getByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("ACME-1")).toBeInTheDocument();
    expect(screen.getByText("Acme Product Pack")).toBeInTheDocument();
    expect(screen.getByText("matched")).toBeInTheDocument();
    expect(screen.getByText("sku")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("renders empty states safely for review tabs", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Weak Mappings" }));
    expect(await screen.findByText("No weak mappings found.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));
    expect(await screen.findByText("No supplier mappings found.")).toBeInTheDocument();
  });

  it("shows weak mapping review details when available", async () => {
    vi.mocked(fetchWeakMappings).mockResolvedValue([mockWeakMapping()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Weak Mappings" }));

    expect(await screen.findByText("Questionable Product")).toBeInTheDocument();
    expect(screen.getByText("Maybe Supplier")).toBeInTheDocument();
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
    expect(screen.getByText("MAYBE-2")).toBeInTheDocument();
  });
});
