import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  fetchProductForecast,
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
} from "./api";
import type { ForecastResponse, Product, ProductSupplierMapping, WeakMapping } from "./types";

vi.mock("./api", () => ({
  fetchProducts: vi.fn(),
  fetchUnmappedProducts: vi.fn(),
  fetchWeakMappings: vi.fn(),
  fetchProductSuppliers: vi.fn(),
  fetchProductForecast: vi.fn(),
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

function mockForecast(overrides: Partial<ForecastResponse> = {}): ForecastResponse {
  return {
    product_id: 1,
    product_name: "Mapped Product",
    current_stock: 12,
    inventory_source: "product_record",
    avg_daily_usage: 1.5,
    days_until_stockout: 8,
    supplier_name: "Acme Supplies",
    matched_sku: "ACME-1",
    lead_time_days_used: 4,
    lead_time_source: "product_supplier",
    supplier_context: {
      supplier_id: 10,
      supplier_name: "Acme Supplies",
      supplier_sku: "ACME-1",
      supplier_product_name: "Acme Product Pack",
      purchase_price: 9.5,
      currency: "USD",
      lead_time_days: 4,
      lead_time_source: "product_supplier",
      minimum_order_quantity: 6,
      moq_source: "product_supplier",
      match_status: "matched",
      match_method: "sku",
      mapping_source: "product_supplier",
      has_supplier_mapping: true,
      needs_supplier_mapping: false,
    },
    reorder_point: 6,
    recommended_action: "monitor",
    recommended_qty: 0,
    risk_level: "low",
    explanation: "Current stock is sufficient.",
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(fetchProducts).mockResolvedValue([]);
  vi.mocked(fetchUnmappedProducts).mockResolvedValue([]);
  vi.mocked(fetchWeakMappings).mockResolvedValue([]);
  vi.mocked(fetchProductSuppliers).mockResolvedValue([]);
  vi.mocked(fetchProductForecast).mockResolvedValue(mockForecast());
});

describe("App mapping review workflow", () => {
  it("renders navigation tabs", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unmapped Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weak Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forecast" })).toBeInTheDocument();
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

  it("renders supplier context for a product forecast", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("Mapped Product (1)")).toBeInTheDocument();
    expect(screen.getByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("ACME-1")).toBeInTheDocument();
    expect(screen.getByText("Acme Product Pack")).toBeInTheDocument();
    expect(screen.getByText("9.5 USD")).toBeInTheDocument();
    expect(screen.getByText("ProductSupplier clean mapping")).toBeInTheDocument();
    expect(screen.getByText("6 (product_supplier)")).toBeInTheDocument();
  });

  it("does not crash when supplier context is missing", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(mockForecast({ supplier_context: null }));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("No supplier context returned.")).toBeInTheDocument();
  });

  it("shows a warning when supplier mapping is needed", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        supplier_context: {
          supplier_id: null,
          supplier_name: null,
          supplier_sku: null,
          supplier_product_name: null,
          purchase_price: null,
          currency: null,
          lead_time_days: 0,
          lead_time_source: "missing",
          minimum_order_quantity: 0,
          moq_source: "missing",
          match_status: null,
          match_method: null,
          mapping_source: "missing",
          has_supplier_mapping: false,
          needs_supplier_mapping: true,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(
      await screen.findByText(
        "This product needs supplier mapping before purchasing recommendations can be trusted.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing supplier mapping")).toBeInTheDocument();
  });

  it("labels fallback supplier mapping sources clearly", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        supplier_context: {
          supplier_id: 11,
          supplier_name: "Fallback Supplier",
          supplier_sku: "FALLBACK-1",
          supplier_product_name: "Fallback Product",
          purchase_price: null,
          currency: null,
          lead_time_days: 5,
          lead_time_source: "supplier_master",
          minimum_order_quantity: 2,
          moq_source: "product_record",
          match_status: "matched",
          match_method: "import_match",
          mapping_source: "product_master_item",
          has_supplier_mapping: true,
          needs_supplier_mapping: false,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("ProductMasterItem fallback")).toBeInTheDocument();
    expect(screen.getByText("Fallback Supplier")).toBeInTheDocument();
  });
});
