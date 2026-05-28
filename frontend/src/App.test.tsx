import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  confirmProductSupplier,
  addPurchaseOrderLine,
  approvePurchaseOrder,
  cancelPurchaseOrder,
  createDraftPurchaseOrderFromProducts,
  createPurchaseOrder,
  createProductSupplier,
  fetchProductForecast,
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
  getPurchaseOrder,
  issuePurchaseOrder,
  listPurchaseOrders,
  receivePurchaseOrder,
  rejectProductSupplier,
  setPreferredProductSupplier,
  submitPurchaseOrderForApproval,
  unsetPreferredProductSupplier,
} from "./api";
import type { ForecastResponse, Product, ProductSupplierMapping, PurchaseOrder, WeakMapping } from "./types";

vi.mock("./api", () => ({
  fetchProducts: vi.fn(),
  fetchUnmappedProducts: vi.fn(),
  fetchWeakMappings: vi.fn(),
  fetchProductSuppliers: vi.fn(),
  fetchProductForecast: vi.fn(),
  createProductSupplier: vi.fn(),
  confirmProductSupplier: vi.fn(),
  rejectProductSupplier: vi.fn(),
  setPreferredProductSupplier: vi.fn(),
  unsetPreferredProductSupplier: vi.fn(),
  listPurchaseOrders: vi.fn(),
  getPurchaseOrder: vi.fn(),
  createDraftPurchaseOrderFromProducts: vi.fn(),
  createPurchaseOrder: vi.fn(),
  addPurchaseOrderLine: vi.fn(),
  updatePurchaseOrderLine: vi.fn(),
  submitPurchaseOrderForApproval: vi.fn(),
  approvePurchaseOrder: vi.fn(),
  issuePurchaseOrder: vi.fn(),
  receivePurchaseOrder: vi.fn(),
  cancelPurchaseOrder: vi.fn(),
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

function mockPurchaseOrder(overrides: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: 500,
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    status: "draft",
    created_at: "2026-05-28T10:00:00",
    updated_at: "2026-05-28T10:00:00",
    approved_at: null,
    issued_at: null,
    received_at: null,
    cancelled_at: null,
    notes: "Draft PO",
    total_amount: 19,
    currency: "USD",
    created_by: "tester",
    approved_by: null,
    lines: [
      {
        id: 700,
        purchase_order_id: 500,
        product_id: 1,
        product_name: null,
        product_supplier_id: 100,
        supplier_sku: "ACME-1",
        supplier_product_name: "Acme Product Pack",
        quantity: 2,
        unit_cost: 9.5,
        currency: "USD",
        line_total: 19,
        minimum_order_quantity: 1,
        pack_size: 1,
        lead_time_days: 4,
        notes: "Line notes",
      },
    ],
    ...overrides,
  };
}

function mockDraftFromProductsResponse(overrides: Partial<PurchaseOrder> = {}) {
  return {
    purchase_order: mockPurchaseOrder(overrides),
    summary: {
      created_line_count: 1,
      skipped_products: [],
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchProducts).mockResolvedValue([]);
  vi.mocked(fetchUnmappedProducts).mockResolvedValue([]);
  vi.mocked(fetchWeakMappings).mockResolvedValue([]);
  vi.mocked(fetchProductSuppliers).mockResolvedValue([]);
  vi.mocked(fetchProductForecast).mockResolvedValue(mockForecast());
  vi.mocked(createProductSupplier).mockResolvedValue(mockSupplierMapping());
  vi.mocked(confirmProductSupplier).mockResolvedValue(mockSupplierMapping({ match_status: "confirmed" }));
  vi.mocked(rejectProductSupplier).mockResolvedValue(mockSupplierMapping({ match_status: "rejected" }));
  vi.mocked(setPreferredProductSupplier).mockResolvedValue(mockSupplierMapping({ is_preferred: true }));
  vi.mocked(unsetPreferredProductSupplier).mockResolvedValue(mockSupplierMapping({ is_preferred: false }));
  vi.mocked(listPurchaseOrders).mockResolvedValue([]);
  vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue(
    mockDraftFromProductsResponse({ status: "draft" }),
  );
  vi.mocked(createPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(addPurchaseOrderLine).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(submitPurchaseOrderForApproval).mockResolvedValue(
    mockPurchaseOrder({ status: "pending_approval" }),
  );
  vi.mocked(approvePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({
      status: "approved",
      approved_at: "2026-05-28T11:00:00",
      approved_by: "manager",
    }),
  );
  vi.mocked(issuePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "issued", issued_at: "2026-05-28T12:00:00" }),
  );
  vi.mocked(receivePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "received", received_at: "2026-05-28T13:00:00" }),
  );
  vi.mocked(cancelPurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "cancelled", cancelled_at: "2026-05-28T11:00:00" }),
  );
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("App mapping review workflow", () => {
  it("renders navigation tabs", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unmapped Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weak Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forecast" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Purchase Orders" })).toBeInTheDocument();
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

  it("selects mapped products for draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 7,
        name: "Selectable Product",
        preferred_supplier: "Draft Supplier",
        preferred_supplier_id: 6,
      }),
    ]);

    render(<App />);

    await screen.findByText("Selectable Product");
    await userEvent.click(screen.getByLabelText("Select Selectable Product for draft PO"));

    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByText("7 · Selectable Product · Draft Supplier")).toBeInTheDocument();
    expect(screen.getByText("Preferred supplier IDs in selection: 6")).toBeInTheDocument();
  });

  it("keeps generate draft PO disabled when no products are selected", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);

    render(<App />);

    await screen.findByText("Mapped Product");
    expect(screen.getByRole("button", { name: "Generate Draft PO" })).toBeDisabled();
    expect(screen.getByText("Select mapped products from the table below.")).toBeInTheDocument();
  });

  it("requires supplier_id before generating a draft PO", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.clear(screen.getByLabelText("Supplier ID"));
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(await screen.findByText("Supplier ID is required.")).toBeInTheDocument();
    expect(createDraftPurchaseOrderFromProducts).not.toHaveBeenCalled();
  });

  it("disables unmapped products for draft PO selection", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 8,
        name: "Unmapped Product",
        mapping_status: "unmapped",
        supplier_count: 0,
        preferred_supplier: null,
        preferred_supplier_id: null,
      }),
    ]);

    render(<App />);

    await screen.findByText("Unmapped Product");
    expect(screen.getByLabelText("Select Unmapped Product for draft PO")).toBeDisabled();
  });

  it("generates a draft PO and displays the result", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 7,
        name: "Mapped Product",
        preferred_supplier_id: 6,
      }),
    ]);
    vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue(
      mockDraftFromProductsResponse({ id: 501, status: "draft" }),
    );

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(createDraftPurchaseOrderFromProducts).toHaveBeenCalledWith({
      supplier_id: 6,
      product_ids: [7],
      created_by: "manual",
      notes: "Draft generated from product selection",
    });
    const resultPanel = await screen.findByLabelText("Draft PO generation result");
    expect(within(resultPanel).getByText("Draft PO 501 created")).toBeInTheDocument();
    expect(within(resultPanel).getByText("draft")).toBeInTheDocument();
    expect(within(resultPanel).getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Draft PO" })).toBeInTheDocument();
  });

  it("displays skipped product summary after draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);
    vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue({
      purchase_order: mockPurchaseOrder({ id: 502, status: "draft" }),
      summary: {
        created_line_count: 1,
        skipped_products: [
          {
            product_id: 9,
            product_name: "Skipped Product",
            reason: "No ProductSupplier mapping exists for this product.",
          },
        ],
      },
    });

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(await screen.findByText("Skipped Products")).toBeInTheDocument();
    expect(
      screen.getByText("Skipped Product: No ProductSupplier mapping exists for this product."),
    ).toBeInTheDocument();
  });

  it("displays backend errors from draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);
    vi.mocked(createDraftPurchaseOrderFromProducts).mockRejectedValue(
      new Error("No valid purchase order lines could be created."),
    );

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(
      await screen.findByText(
        "Draft generation failed: No valid purchase order lines could be created.",
      ),
    ).toBeInTheDocument();
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

  it("confirm button calls the confirm endpoint and refreshes mappings", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(confirmProductSupplier).toHaveBeenCalledWith(100);
    expect(fetchProductSuppliers).toHaveBeenCalledTimes(2);
  });

  it("reject button confirms before calling the reject endpoint", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(window.confirm).toHaveBeenCalledWith("Reject this supplier mapping?");
    expect(rejectProductSupplier).toHaveBeenCalledWith(100);
  });

  it("set preferred button calls the set-preferred endpoint", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Set Preferred" }));

    expect(setPreferredProductSupplier).toHaveBeenCalledWith(100);
  });

  it("validates product_id and supplier_id before creating a mapping", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(await screen.findByText("Product ID is required.")).toBeInTheDocument();
    expect(createProductSupplier).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Product ID"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(await screen.findByText("Supplier ID is required.")).toBeInTheDocument();
    expect(createProductSupplier).not.toHaveBeenCalled();
  });

  it("creates mapping with default manual review fields", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "2");
    await userEvent.type(screen.getByLabelText("Supplier ID"), "3");
    await userEvent.type(screen.getByLabelText("Supplier SKU"), "NEW-SKU");
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(createProductSupplier).toHaveBeenCalledWith(
      expect.objectContaining({
        product_id: 2,
        supplier_id: 3,
        supplier_sku: "NEW-SKU",
        match_status: "needs_review",
        match_method: "manual",
      }),
    );
  });

  it("displays rejected mapping status distinctly", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([
      mockSupplierMapping({ is_preferred: false, match_status: "rejected" }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mappings" }));

    const rejected = await screen.findByText("rejected");
    expect(rejected).toHaveClass("rejected");
  });

  it("purchase orders tab renders and lists a draft PO", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));

    expect(await screen.findByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.getByText("Draft PO")).toBeInTheDocument();
    expect(screen.getByText("19")).toBeInTheDocument();
  });

  it("create draft PO form validates supplier_id", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(screen.getByRole("button", { name: "Create Draft PO" }));

    expect(await screen.findByText("Supplier ID is required.")).toBeInTheDocument();
    expect(createPurchaseOrder).not.toHaveBeenCalled();
  });

  it("add line form validates product supplier and quantity", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(await screen.findByText("ProductSupplier ID is required.")).toBeInTheDocument();
    expect(addPurchaseOrderLine).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("ProductSupplier ID"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(await screen.findByText("Quantity must be greater than zero.")).toBeInTheDocument();
    expect(addPurchaseOrderLine).not.toHaveBeenCalled();
  });

  it("shows backend error when adding an invalid PO line", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(addPurchaseOrderLine).mockRejectedValue(
      new Error("ProductSupplier belongs to a different supplier."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.type(screen.getByLabelText("ProductSupplier ID"), "101");
    await userEvent.type(screen.getByLabelText("Quantity"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(
      await screen.findByText(
        "Purchase order action failed: ProductSupplier belongs to a different supplier.",
      ),
    ).toBeInTheDocument();
  });

  it("submit for approval calls the correct endpoint", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Submit for Approval" }));

    expect(submitPurchaseOrderForApproval).toHaveBeenCalledWith(500);
  });

  it("cancel purchase order asks for confirmation", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(window.confirm).toHaveBeenCalledWith("Cancel this purchase order?");
    expect(cancelPurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("pending approval PO shows approve action and hides line editing", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("approved PO shows issue action and no line editing", async () => {
    const approvedPo = mockPurchaseOrder({
      status: "approved",
      approved_at: "2026-05-28T11:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([approvedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(approvedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Issue" })).toBeInTheDocument();
    expect(
      screen.getByText("Issue only marks this PO as internally issued. It does not send it externally."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
  });

  it("issued PO shows receive action and no line editing", async () => {
    const issuedPo = mockPurchaseOrder({
      status: "issued",
      approved_at: "2026-05-28T11:00:00",
      issued_at: "2026-05-28T12:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Receive" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
  });

  it("received PO shows no workflow action buttons", async () => {
    const receivedPo = mockPurchaseOrder({
      status: "received",
      approved_at: "2026-05-28T11:00:00",
      issued_at: "2026-05-28T12:00:00",
      received_at: "2026-05-28T13:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([receivedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(receivedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");

    expect(screen.queryByRole("button", { name: "Submit for Approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Issue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Receive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("cancelled PO shows no workflow action buttons", async () => {
    const cancelledPo = mockPurchaseOrder({
      status: "cancelled",
      cancelled_at: "2026-05-28T11:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([cancelledPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(cancelledPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");

    expect(screen.queryByRole("button", { name: "Submit for Approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Issue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Receive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("approve action calls the approve endpoint with approved_by", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.type(await screen.findByLabelText("Approved by"), "manager");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(approvePurchaseOrder).toHaveBeenCalledWith(500, { approved_by: "manager" });
  });

  it("issue action confirms before calling the issue endpoint", async () => {
    const approvedPo = mockPurchaseOrder({ status: "approved" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([approvedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(approvedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Issue" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Mark this purchase order as internally issued? This will not send it externally.",
    );
    expect(issuePurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("receive action confirms before calling the receive endpoint", async () => {
    const issuedPo = mockPurchaseOrder({ status: "issued" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Receive" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Mark this purchase order as received? This will not update stock yet.",
    );
    expect(receivePurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("shows backend errors from approval workflow actions", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);
    vi.mocked(approvePurchaseOrder).mockRejectedValue(
      new Error("Cannot approve a purchase order with no lines."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText(
        "Purchase order action failed: Cannot approve a purchase order with no lines.",
      ),
    ).toBeInTheDocument();
  });
});
