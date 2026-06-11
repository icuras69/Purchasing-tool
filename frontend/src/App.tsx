import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  confirmProductSupplier,
  confirmSupplierAssignmentReview,
  addPurchaseOrderLine,
  approvePurchaseOrder,
  cancelPurchaseOrder,
  acceptRecommendation,
  convertRecommendationToDraftPO,
  createDraftPOFromSupplierForecast,
  createDraftPurchaseOrderFromProducts,
  createPurchaseOrder,
  createProductSupplier,
  createReorderRecommendation,
  fetchProductForecast,
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
  generateRecommendationLLMExplanation,
  getForecastReadinessRows,
  getForecastReadinessSummary,
  getSupplierAssignmentReviewItems,
  getSupplierAssignmentReviewSummary,
  getProductSeasonality,
  getPurchaseOrder,
  getRecommendation,
  getSeasonalProducts,
  getSeasonalitySummary,
  getSupplierForecast,
  issuePurchaseOrder,
  listRecommendations,
  listPurchaseOrders,
  listSuppliers,
  receivePurchaseOrder,
  rejectRecommendation,
  rejectProductSupplier,
  rejectSupplierAssignmentReview,
  setPreferredProductSupplier,
  submitPurchaseOrderForApproval,
  unsetPreferredProductSupplier,
  updatePurchaseOrderLine,
} from "./api";
import { productMatchesQuery, supplierDisplayName } from "./productDisplay";
import type {
  ForecastResponse,
  ForecastInputAudit,
  ForecastReadinessSummary,
  ForecastSupplierContext,
  RecommendationLLMExplanation,
  ProductSeasonalityDetail,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  PurchaseOrder,
  PurchaseRecommendation,
  AddPurchaseOrderLineRequest,
  CreatePurchaseOrderRequest,
  DraftFromProductsResponse,
  SeasonalProduct,
  SeasonalitySummary,
  SupplierAssignmentReviewItem,
  SupplierAssignmentReviewSummary,
  SupplierForecastResponse,
  SupplierOption,
  UpdatePurchaseOrderLineRequest,
  WeakMapping,
} from "./types";

type TabId =
  | "products"
  | "unmapped"
  | "weak"
  | "mappings"
  | "forecast"
  | "supplier-forecast"
  | "forecast-readiness"
  | "supplier-assignment-review"
  | "seasonality"
  | "purchase-orders"
  | "recommendations";

type SupplierForecastFilter =
  | "all"
  | "needs_reorder"
  | "high_risk"
  | "open_demand"
  | "no_history"
  | "missing_lead_time";

interface ResourceState<T> {
  data: T[];
  loading: boolean;
  error: string | null;
}

const tabs: Array<{ id: TabId; label: string }> = [
  { id: "products", label: "Products" },
  { id: "unmapped", label: "Unmapped Products" },
  { id: "weak", label: "Weak Mappings" },
  { id: "mappings", label: "Supplier Mappings" },
  { id: "forecast", label: "Forecast" },
  { id: "supplier-forecast", label: "Supplier Forecast" },
  { id: "forecast-readiness", label: "Forecast Readiness" },
  { id: "supplier-assignment-review", label: "Supplier Assignment Review" },
  { id: "seasonality", label: "Seasonality" },
  { id: "purchase-orders", label: "Purchase Orders" },
  { id: "recommendations", label: "Recommendations" },
];

const monthNames = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const seasonalityStatusPriority: Record<string, number> = {
  in_season: 5,
  approaching_season: 4,
  year_round: 3,
  off_season: 2,
  insufficient_data: 1,
};

const confidencePriority: Record<string, number> = {
  high: 4,
  medium: 3,
  low: 2,
  insufficient: 1,
};

function initialResource<T>(): ResourceState<T> {
  return {
    data: [],
    loading: true,
    error: null,
  };
}

function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function formatPrice(mapping: Pick<ProductSupplierMapping, "purchase_price" | "currency">): string {
  if (mapping.purchase_price === null || mapping.purchase_price === undefined) {
    return "-";
  }
  return `${mapping.purchase_price}${mapping.currency ? ` ${mapping.currency}` : ""}`;
}

function mappingSourceLabel(mappingSource: string | null | undefined): string {
  if (mappingSource === "product_supplier") {
    return "Legacy ProductSupplier mapping";
  }
  if (mappingSource === "orderpro_product_supplier") {
    return "OrderPro product supplier";
  }
  if (mappingSource === "product_master_item") {
    return "ProductMasterItem fallback";
  }
  if (mappingSource === "legacy_product") {
    return "Legacy product fallback";
  }
  if (mappingSource === "missing") {
    return "Missing supplier mapping";
  }
  return formatValue(mappingSource);
}

function formatBoolean(value: boolean): string {
  return value ? "Yes" : "No";
}

function statusClassName(status: string | null | undefined): string {
  const normalized = status ?? "unknown";
  if (normalized === "confirmed" || normalized === "matched") {
    return "status mapped";
  }
  if (normalized === "rejected") {
    return "status rejected";
  }
  return "status needs-review";
}

function purchaseOrderStatusClassName(status: string): string {
  if (status === "draft") {
    return "status needs-review";
  }
  if (status === "pending_approval") {
    return "status pending-approval";
  }
  if (status === "approved") {
    return "status approved";
  }
  if (status === "issued") {
    return "status issued";
  }
  if (status === "received") {
    return "status received";
  }
  if (status === "cancelled") {
    return "status rejected";
  }
  return "status mapped";
}

function recommendationStatusClassName(status: string): string {
  if (status === "accepted" || status === "converted_to_po") {
    return "status mapped";
  }
  if (status === "rejected") {
    return "status rejected";
  }
  if (status === "pending_review" || status === "draft") {
    return "status pending-approval";
  }
  return "status needs-review";
}

function forecastRiskClassName(riskLevel: string | null | undefined): string {
  if (riskLevel === "high" || riskLevel === "critical") {
    return "status rejected";
  }
  if (riskLevel === "medium") {
    return "status needs-review";
  }
  return "status mapped";
}

function demandSourceLabel(source: string | null | undefined): string {
  if (source === "orderpro_orders") {
    return "OrderPro orders";
  }
  if (source === "usage_history") {
    return "Legacy usage history";
  }
  if (source === "none") {
    return "No demand history";
  }
  if (source === "not_applicable") {
    return "Not applicable";
  }
  return formatValue(source);
}

function forecastNeedsReorder(row: ForecastResponse): boolean {
  return Number(row.recommended_qty || 0) > 0;
}

function forecastHasOpenDemand(row: ForecastResponse): boolean {
  return Number(row.total_open_demand || 0) > 0;
}

function forecastHasNoDemandHistory(row: ForecastResponse): boolean {
  return row.demand_source === "none" || Number(row.shipped_order_count || 0) === 0;
}

function forecastMissingLeadTime(row: ForecastResponse): boolean {
  return Number(row.lead_time_days_used || 0) <= 0 || row.lead_time_source === "missing";
}

function seasonalityStatusLabel(status: string | null | undefined): string {
  if (status === "in_season") return "In season";
  if (status === "approaching_season") return "Approaching season";
  if (status === "off_season") return "Off season";
  if (status === "year_round") return "Year-round";
  if (status === "insufficient_data") return "Insufficient data";
  return formatValue(status);
}

function seasonalityTagLabel(tag: string | null | undefined): string {
  if (tag === "winter") return "Winter";
  if (tag === "spring") return "Spring";
  if (tag === "summer") return "Summer";
  if (tag === "autumn") return "Autumn";
  if (tag === "multi_peak") return "Multi-peak";
  if (tag === "year_round") return "Year-round";
  if (tag === "insufficient_data") return "Insufficient data";
  return formatValue(tag);
}

function seasonalityStatusClassName(status: string | null | undefined): string {
  if (status === "in_season" || status === "year_round") return "status mapped";
  if (status === "approaching_season") return "status pending-approval";
  if (status === "insufficient_data") return "status rejected";
  return "status needs-review";
}

function stockStatus(product: Pick<SeasonalProduct, "current_stock">): string {
  if (Number(product.current_stock || 0) <= 0) return "out_of_stock";
  if (Number(product.current_stock || 0) <= 5) return "low_stock";
  return "in_stock";
}

function formatMonth(month: number): string {
  return monthNames[month - 1] ?? `Month ${month}`;
}

function formatMonths(months: number[]): string {
  return months.length ? months.map(formatMonth).join(", ") : "-";
}

function forecastMatchesFilter(row: ForecastResponse, filter: SupplierForecastFilter): boolean {
  if (filter === "needs_reorder") {
    return forecastNeedsReorder(row);
  }
  if (filter === "high_risk") {
    return row.risk_level === "high" || row.risk_level === "critical";
  }
  if (filter === "open_demand") {
    return forecastHasOpenDemand(row);
  }
  if (filter === "no_history") {
    return forecastHasNoDemandHistory(row);
  }
  if (filter === "missing_lead_time") {
    return forecastMissingLeadTime(row);
  }
  return true;
}

function sortSupplierForecastRows(rows: ForecastResponse[]): ForecastResponse[] {
  return [...rows].sort((left, right) => {
    const leftPriority = forecastNeedsReorder(left) ? 1 : 0;
    const rightPriority = forecastNeedsReorder(right) ? 1 : 0;
    if (leftPriority !== rightPriority) {
      return rightPriority - leftPriority;
    }
    const leftRisk = left.risk_level === "high" || left.risk_level === "critical" ? 1 : 0;
    const rightRisk = right.risk_level === "high" || right.risk_level === "critical" ? 1 : 0;
    if (leftRisk !== rightRisk) {
      return rightRisk - leftRisk;
    }
    const quantityDiff = Number(right.recommended_qty || 0) - Number(left.recommended_qty || 0);
    if (quantityDiff !== 0) {
      return quantityDiff;
    }
    return left.product_name.localeCompare(right.product_name);
  });
}

function snapshotValue(snapshot: Record<string, unknown> | null | undefined, key: string): string {
  const value = snapshot?.[key];
  if (typeof value === "string" || typeof value === "number") {
    return formatValue(value);
  }
  if (typeof value === "boolean") {
    return formatBoolean(value);
  }
  return "-";
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function weakMappingReason(mapping: WeakMapping): string {
  if (mapping.reason) {
    return mapping.reason;
  }
  if (!mapping.supplier_id) {
    return "No supplier mapping";
  }
  if (mapping.match_status && mapping.match_status !== "matched") {
    return `Match status: ${mapping.match_status}`;
  }
  if (mapping.match_confidence !== null && mapping.match_confidence !== undefined) {
    return `Low confidence: ${mapping.match_confidence}`;
  }
  return "Needs review";
}

function matchesText(values: Array<string | number | null | undefined>, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  return values
    .map((value) => formatValue(value))
    .join(" ")
    .toLowerCase()
    .includes(normalized);
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("products");
  const [products, setProducts] = useState<ResourceState<Product>>(initialResource);
  const [unmappedProducts, setUnmappedProducts] = useState<ResourceState<Product>>(initialResource);
  const [weakMappings, setWeakMappings] = useState<ResourceState<WeakMapping>>(initialResource);
  const [supplierMappings, setSupplierMappings] =
    useState<ResourceState<ProductSupplierMapping>>(initialResource);
  const [expandedProductId, setExpandedProductId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [actionMappingId, setActionMappingId] = useState<number | null>(null);
  const [mappingActionError, setMappingActionError] = useState<string | null>(null);
  const [createMappingError, setCreateMappingError] = useState<string | null>(null);
  const [createMappingSuccess, setCreateMappingSuccess] = useState<string | null>(null);
  const [creatingMapping, setCreatingMapping] = useState(false);
  const [selectedProductIdsForDraft, setSelectedProductIdsForDraft] = useState<number[]>([]);
  const [poToViewId, setPoToViewId] = useState<number | null>(null);

  const loadProducts = useCallback((active = true) => {
    fetchProducts()
      .then((loadedProducts) => {
        if (active) {
          setProducts({ data: loadedProducts, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setProducts({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  const loadUnmappedProducts = useCallback((active = true) => {
    fetchUnmappedProducts()
      .then((loadedProducts) => {
        if (active) {
          setUnmappedProducts({ data: loadedProducts, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setUnmappedProducts({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  const loadWeakMappings = useCallback((active = true) => {
    fetchWeakMappings()
      .then((loadedMappings) => {
        if (active) {
          setWeakMappings({ data: loadedMappings, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setWeakMappings({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  const loadSupplierMappings = useCallback((active = true) => {
    fetchProductSuppliers()
      .then((loadedMappings) => {
        if (active) {
          setSupplierMappings({ data: loadedMappings, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setSupplierMappings({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  const refreshMappingReview = useCallback(() => {
    loadProducts();
    loadUnmappedProducts();
    loadWeakMappings();
    loadSupplierMappings();
  }, [loadProducts, loadSupplierMappings, loadUnmappedProducts, loadWeakMappings]);

  useEffect(() => {
    let active = true;

    loadProducts(active);
    loadUnmappedProducts(active);
    loadWeakMappings(active);
    loadSupplierMappings(active);

    return () => {
      active = false;
    };
  }, [loadProducts, loadSupplierMappings, loadUnmappedProducts, loadWeakMappings]);

  async function runMappingAction(
    mappingId: number,
    action: () => Promise<ProductSupplierMapping>,
  ) {
    setActionMappingId(mappingId);
    setMappingActionError(null);
    try {
      await action();
      refreshMappingReview();
    } catch (loadError) {
      setMappingActionError((loadError as Error).message);
    } finally {
      setActionMappingId(null);
    }
  }

  async function handleReject(mappingId: number) {
    if (!window.confirm("Reject this supplier mapping?")) {
      return;
    }
    await runMappingAction(mappingId, () => rejectProductSupplier(mappingId));
  }

  async function handleCreateMapping(payload: ProductSupplierInput) {
    setCreatingMapping(true);
    setCreateMappingError(null);
    setCreateMappingSuccess(null);
    try {
      await createProductSupplier(payload);
      setCreateMappingSuccess("Mapping created.");
      refreshMappingReview();
    } catch (loadError) {
      setCreateMappingError((loadError as Error).message);
    } finally {
      setCreatingMapping(false);
    }
  }

  function toggleProductForDraft(productId: number) {
    setSelectedProductIdsForDraft((current) =>
      current.includes(productId)
        ? current.filter((selectedId) => selectedId !== productId)
        : [...current, productId],
    );
  }

  function handleViewGeneratedPo(poId: number) {
    setPoToViewId(poId);
    setActiveTab("purchase-orders");
  }

  const filteredProducts = useMemo(
    () => products.data.filter((product) => productMatchesQuery(product, query)),
    [products.data, query],
  );

  const filteredUnmappedProducts = useMemo(
    () => unmappedProducts.data.filter((product) => productMatchesQuery(product, query)),
    [unmappedProducts.data, query],
  );

  const filteredWeakMappings = useMemo(
    () =>
      weakMappings.data.filter((mapping) =>
        matchesText(
          [
            mapping.product_name,
            mapping.supplier_name,
            mapping.supplier_sku,
            mapping.supplier_product_name,
            mapping.reason,
            mapping.match_status,
            mapping.match_method,
          ],
          query,
        ),
      ),
    [weakMappings.data, query],
  );

  const filteredSupplierMappings = useMemo(
    () =>
      supplierMappings.data.filter((mapping) =>
        matchesText(
          [
            mapping.product_name,
            mapping.supplier_name,
            mapping.supplier_sku,
            mapping.supplier_product_name,
            mapping.match_status,
            mapping.match_method,
          ],
          query,
        ),
      ),
    [supplierMappings.data, query],
  );

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>Purchasing AI</h1>
          <p>Product supplier mapping review</p>
        </div>
        <label className="search-label">
          <span>Search</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Product, supplier, or SKU"
          />
        </label>
      </header>

      <nav className="tabs" aria-label="Mapping review sections">
        {tabs.map((tab) => (
          <button
            className={activeTab === tab.id ? "tab active" : "tab"}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "products" && (
        <div className="review-stack">
          <DraftPoFromProductsPanel
            onViewPurchaseOrder={handleViewGeneratedPo}
            products={products.data}
            selectedProductIds={selectedProductIdsForDraft}
          />
          <ProductTable
            expandedProductId={expandedProductId}
            onExpandedProductIdChange={setExpandedProductId}
            onToggleDraftSelection={toggleProductForDraft}
            products={filteredProducts}
            resource={products}
            selectedProductIds={selectedProductIdsForDraft}
          />
        </div>
      )}

      {activeTab === "unmapped" && (
        <UnmappedProductsTable
          createError={createMappingError}
          createSuccess={createMappingSuccess}
          creating={creatingMapping}
          onCreateMapping={handleCreateMapping}
          products={filteredUnmappedProducts}
          resource={unmappedProducts}
        />
      )}

      {activeTab === "weak" && (
        <WeakMappingsTable
          actionError={mappingActionError}
          actionMappingId={actionMappingId}
          mappings={filteredWeakMappings}
          onConfirm={(mappingId) =>
            runMappingAction(mappingId, () => confirmProductSupplier(mappingId))
          }
          onReject={handleReject}
          resource={weakMappings}
        />
      )}

      {activeTab === "mappings" && (
        <SupplierMappingsTable
          actionError={mappingActionError}
          actionMappingId={actionMappingId}
          mappings={filteredSupplierMappings}
          onConfirm={(mappingId) =>
            runMappingAction(mappingId, () => confirmProductSupplier(mappingId))
          }
          onReject={handleReject}
          onSetPreferred={(mappingId) =>
            runMappingAction(mappingId, () => setPreferredProductSupplier(mappingId))
          }
          onUnsetPreferred={(mappingId) =>
            runMappingAction(mappingId, () => unsetPreferredProductSupplier(mappingId))
          }
          resource={supplierMappings}
        />
      )}

      {activeTab === "forecast" && <ForecastPanel />}

      {activeTab === "supplier-forecast" && (
        <SupplierForecastPanel onViewPurchaseOrder={handleViewGeneratedPo} />
      )}

      {activeTab === "forecast-readiness" && <ForecastReadinessPanel />}

      {activeTab === "supplier-assignment-review" && <SupplierAssignmentReviewPanel />}

      {activeTab === "seasonality" && <SeasonalityPanel />}

      {activeTab === "purchase-orders" && <PurchaseOrdersPanel initialPoId={poToViewId} />}

      {activeTab === "recommendations" && <RecommendationsPanel />}
    </main>
  );
}

interface ProductTableProps {
  expandedProductId: number | null;
  onExpandedProductIdChange: (productId: number | null) => void;
  onToggleDraftSelection: (productId: number) => void;
  products: Product[];
  resource: ResourceState<Product>;
  selectedProductIds: number[];
}

function ProductTable({
  expandedProductId,
  onExpandedProductIdChange,
  onToggleDraftSelection,
  products,
  resource,
  selectedProductIds,
}: ProductTableProps) {
  if (resource.loading) {
    return <div className="state">Loading products...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load products: {resource.error}</div>;
  }

  return (
    <section className="table-wrap" aria-label="Product list">
      <table>
        <thead>
          <tr>
            <th>Select</th>
            <th>Product ID</th>
            <th>OrderPro SKU</th>
            <th>Product name</th>
            <th>Current stock</th>
            <th>Active supplier</th>
            <th>Supplier ID</th>
            <th>Supplier count</th>
            <th>Mapping status</th>
            <th>Supplier SKU</th>
            <th>Legacy mappings</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => {
            const isExpanded = expandedProductId === product.id;
            const statusClass = product.supplier_id ? "status mapped" : "status unmapped";
            const displayStatus = product.supplier_id ? "mapped" : "missing supplier";

            return (
              <Fragment key={product.id}>
                <tr>
                  <td>
                    <input
                      aria-label={`Select ${product.name} for draft PO`}
                      checked={selectedProductIds.includes(product.id)}
                      disabled={!product.supplier_id}
                      onChange={() => onToggleDraftSelection(product.id)}
                      type="checkbox"
                    />
                  </td>
                  <td>{product.id}</td>
                  <td>{formatValue(product.orderpro_sku)}</td>
                  <td>{product.name}</td>
                  <td>{formatValue(product.current_stock)}</td>
                  <td>{supplierDisplayName(product)}</td>
                  <td>{formatValue(product.supplier_id)}</td>
                  <td>{product.supplier_count}</td>
                  <td>
                    <span className={statusClass}>{displayStatus}</span>
                  </td>
                  <td>{formatValue(product.supplier_sku ?? product.preferred_supplier_sku)}</td>
                  <td>
                    <button
                      disabled={product.supplier_mappings.length === 0}
                      onClick={() => onExpandedProductIdChange(isExpanded ? null : product.id)}
                      type="button"
                    >
                      {isExpanded ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan={11}>
                      <div className="mapping-panel">
                        <table>
                          <thead>
                            <tr>
                              <th>Supplier</th>
                              <th>Supplier SKU</th>
                              <th>Supplier product</th>
                              <th>Price</th>
                              <th>Match status</th>
                              <th>Match method</th>
                              <th>Preferred</th>
                            </tr>
                          </thead>
                          <tbody>
                            {product.supplier_mappings.map((mapping) => (
                              <tr key={mapping.id}>
                                <td>{formatValue(mapping.supplier_name)}</td>
                                <td>{formatValue(mapping.supplier_sku)}</td>
                                <td>{formatValue(mapping.supplier_product_name)}</td>
                                <td>{formatPrice(mapping)}</td>
                                <td>{formatValue(mapping.match_status)}</td>
                                <td>{formatValue(mapping.match_method)}</td>
                                <td>{formatBoolean(mapping.is_preferred)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {products.length === 0 && <div className="state">No products found.</div>}
    </section>
  );
}

function DraftPoFromProductsPanel({
  onViewPurchaseOrder,
  products,
  selectedProductIds,
}: {
  onViewPurchaseOrder: (poId: number) => void;
  products: Product[];
  selectedProductIds: number[];
}) {
  const [createdBy, setCreatedBy] = useState("manual");
  const [notes, setNotes] = useState("Draft generated from product selection");
  const [onlyReorderNeeded, setOnlyReorderNeeded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [result, setResult] = useState<DraftFromProductsResponse | null>(null);

  const selectedProducts = products.filter((product) => selectedProductIds.includes(product.id));
  const selectedSupplierIds = Array.from(
    new Set(
      selectedProducts
        .map((product) => product.supplier_id)
        .filter((value): value is number => value !== null && value !== undefined),
    ),
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedProductIds.length === 0) {
      setValidationError("Select at least one product with an OrderPro supplier.");
      return;
    }

    setCreating(true);
    setValidationError(null);
    setCreateError(null);
    setResult(null);
    try {
      const created = await createDraftPurchaseOrderFromProducts({
        product_ids: selectedProductIds,
        created_by: createdBy || "manual",
        notes: notes || "Draft generated from product selection",
        only_reorder_needed: onlyReorderNeeded,
      });
      setResult(created);
    } catch (loadError) {
      setCreateError((loadError as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="detail-panel" aria-label="Generate draft purchase order">
      <div className="section-header">
        <h2>Generate Draft PO</h2>
        <span className="action-state">{selectedProductIds.length} selected</span>
      </div>
      <div className="state">
        This only creates a draft purchase order. It does not submit, approve, issue, or send it.
      </div>
      {selectedProducts.length > 0 && (
        <div className="selected-products">
          {selectedProducts.map((product) => (
            <span className="selected-pill" key={product.id}>
              {product.id} · {product.name} · {supplierDisplayName(product)}
            </span>
          ))}
        </div>
      )}
      {selectedSupplierIds.length > 0 && (
        <div className="action-state">
          OrderPro supplier IDs in selection: {selectedSupplierIds.join(", ")}
        </div>
      )}
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Created by</span>
          <input onChange={(event) => setCreatedBy(event.target.value)} value={createdBy} />
        </label>
        <label>
          <span>Notes</span>
          <input onChange={(event) => setNotes(event.target.value)} value={notes} />
        </label>
        <label className="checkbox-label">
          <input
            checked={onlyReorderNeeded}
            onChange={(event) => setOnlyReorderNeeded(event.target.checked)}
            type="checkbox"
          />
          <span>Only include products with reorder need</span>
        </label>
        <button disabled={creating || selectedProductIds.length === 0} type="submit">
          {creating ? "Generating..." : "Generate Draft PO"}
        </button>
      </form>
      {selectedProductIds.length === 0 && (
        <div className="action-state">Select products with an OrderPro supplier from the table below.</div>
      )}
      {validationError && <div className="state error">{validationError}</div>}
      {createError && <div className="state error">Draft generation failed: {createError}</div>}
      {result && (
        <DraftPoGenerationResult onViewPurchaseOrder={onViewPurchaseOrder} result={result} />
      )}
    </section>
  );
}

function DraftPoGenerationResult({
  onViewPurchaseOrder,
  result,
}: {
  onViewPurchaseOrder: (poId: number) => void;
  result: DraftFromProductsResponse;
}) {
  const createdPoCount = result.summary.created_po_count ?? result.created_purchase_orders.length;
  const totalQuantity = result.created_purchase_orders.reduce(
    (sum, po) => sum + po.lines.reduce((lineSum, line) => lineSum + Number(line.quantity || 0), 0),
    0,
  );

  return (
    <div className="result-panel" aria-label="Draft PO generation result">
      <h3>
        {createdPoCount} draft PO{createdPoCount === 1 ? "" : "s"} created
      </h3>
      <dl className="detail-list">
        <div>
          <dt>PO count</dt>
          <dd>{createdPoCount}</dd>
        </div>
        <div>
          <dt>Created lines</dt>
          <dd>{result.summary.created_line_count}</dd>
        </div>
        <div>
          <dt>Total recommended quantity</dt>
          <dd>{totalQuantity}</dd>
        </div>
      </dl>
      {result.created_purchase_orders.length > 0 && (
        <div className="nested-panel">
          <h3>Created Purchase Orders</h3>
          <ul className="skip-list">
            {result.created_purchase_orders.map((po) => (
              <li key={po.id}>
                Draft PO {po.id}: {formatValue(po.supplier_name)}{" "}
                <span className={purchaseOrderStatusClassName(po.status)}>{po.status}</span>{" "}
                <button onClick={() => onViewPurchaseOrder(po.id)} type="button">
                  View Draft PO {po.id}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {createdPoCount === 0 && (
        <div className="state">No draft purchase order was created.</div>
      )}
      {result.summary.grouped_by_supplier && (
        <div className="action-state">
          Grouped by supplier:{" "}
          {Object.entries(result.summary.grouped_by_supplier)
            .map(([supplierId, count]) => `${supplierId}: ${count}`)
            .join(", ")}
        </div>
      )}
      {result.summary.skipped_products.length > 0 && (
        <div className="nested-panel">
          <h3>Skipped Products</h3>
          <ul className="skip-list">
            {result.summary.skipped_products.map((product) => (
              <li key={product.product_id}>
                {product.product_name ?? product.product_id}: {product.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function UnmappedProductsTable({
  createError,
  createSuccess,
  creating,
  onCreateMapping,
  products,
  resource,
}: {
  createError: string | null;
  createSuccess: string | null;
  creating: boolean;
  onCreateMapping: (payload: ProductSupplierInput) => Promise<void>;
  products: Product[];
  resource: ResourceState<Product>;
}) {
  if (resource.loading) {
    return <div className="state">Loading unmapped products...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load unmapped products: {resource.error}</div>;
  }

  return (
    <div className="review-stack">
      <CreateMappingForm
        createError={createError}
        createSuccess={createSuccess}
        creating={creating}
        onCreateMapping={onCreateMapping}
      />
      <section className="table-wrap" aria-label="Unmapped products">
        <table>
          <thead>
            <tr>
              <th>Product ID</th>
              <th>Product name</th>
              <th>Current stock</th>
              <th>Mapping status</th>
              <th>Review need</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <tr key={product.id}>
                <td>{product.id}</td>
                <td>{product.name}</td>
                <td>{formatValue(product.current_stock)}</td>
                <td>
                  <span className="status unmapped">{product.mapping_status}</span>
                </td>
                <td>
                  <span className="review-need">Needs supplier mapping</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {products.length === 0 && <div className="state">No unmapped products found.</div>}
      </section>
    </div>
  );
}

function CreateMappingForm({
  createError,
  createSuccess,
  creating,
  onCreateMapping,
}: {
  createError: string | null;
  createSuccess: string | null;
  creating: boolean;
  onCreateMapping: (payload: ProductSupplierInput) => Promise<void>;
}) {
  const [form, setForm] = useState({
    product_id: "",
    supplier_id: "",
    supplier_sku: "",
    supplier_product_name: "",
    purchase_price: "",
    currency: "",
    minimum_order_quantity: "",
    pack_size: "",
    lead_time_days: "",
    match_status: "needs_review",
    match_method: "manual",
    match_confidence: "",
  });
  const [validationError, setValidationError] = useState<string | null>(null);

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function optionalNumber(value: string): number | null {
    if (value.trim() === "") {
      return null;
    }
    return Number(value);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const productId = Number(form.product_id);
    const supplierId = Number(form.supplier_id);

    if (!Number.isInteger(productId) || productId <= 0) {
      setValidationError("Product ID is required.");
      return;
    }
    if (!Number.isInteger(supplierId) || supplierId <= 0) {
      setValidationError("Supplier ID is required.");
      return;
    }

    setValidationError(null);
    await onCreateMapping({
      product_id: productId,
      supplier_id: supplierId,
      supplier_sku: form.supplier_sku || null,
      supplier_product_name: form.supplier_product_name || null,
      purchase_price: optionalNumber(form.purchase_price),
      currency: form.currency || null,
      minimum_order_quantity: optionalNumber(form.minimum_order_quantity),
      pack_size: optionalNumber(form.pack_size),
      lead_time_days: optionalNumber(form.lead_time_days),
      match_status: form.match_status || "needs_review",
      match_method: form.match_method || "manual",
      match_confidence: optionalNumber(form.match_confidence),
    });
  }

  return (
    <section className="detail-panel" aria-label="Create supplier mapping">
      <h2>Create Mapping</h2>
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Product ID</span>
          <input
            onChange={(event) => updateField("product_id", event.target.value)}
            value={form.product_id}
          />
        </label>
        <label>
          <span>Supplier ID</span>
          <input
            onChange={(event) => updateField("supplier_id", event.target.value)}
            value={form.supplier_id}
          />
        </label>
        <label>
          <span>Supplier SKU</span>
          <input
            onChange={(event) => updateField("supplier_sku", event.target.value)}
            value={form.supplier_sku}
          />
        </label>
        <label>
          <span>Supplier product name</span>
          <input
            onChange={(event) => updateField("supplier_product_name", event.target.value)}
            value={form.supplier_product_name}
          />
        </label>
        <label>
          <span>Purchase price</span>
          <input
            onChange={(event) => updateField("purchase_price", event.target.value)}
            value={form.purchase_price}
          />
        </label>
        <label>
          <span>Currency</span>
          <input onChange={(event) => updateField("currency", event.target.value)} value={form.currency} />
        </label>
        <label>
          <span>Minimum order quantity</span>
          <input
            onChange={(event) => updateField("minimum_order_quantity", event.target.value)}
            value={form.minimum_order_quantity}
          />
        </label>
        <label>
          <span>Pack size</span>
          <input onChange={(event) => updateField("pack_size", event.target.value)} value={form.pack_size} />
        </label>
        <label>
          <span>Lead time days</span>
          <input
            onChange={(event) => updateField("lead_time_days", event.target.value)}
            value={form.lead_time_days}
          />
        </label>
        <label>
          <span>Match status</span>
          <input
            onChange={(event) => updateField("match_status", event.target.value)}
            value={form.match_status}
          />
        </label>
        <label>
          <span>Match method</span>
          <input
            onChange={(event) => updateField("match_method", event.target.value)}
            value={form.match_method}
          />
        </label>
        <label>
          <span>Match confidence</span>
          <input
            onChange={(event) => updateField("match_confidence", event.target.value)}
            value={form.match_confidence}
          />
        </label>
        <button disabled={creating} type="submit">
          {creating ? "Creating..." : "Create Mapping"}
        </button>
      </form>
      {validationError && <div className="state error">{validationError}</div>}
      {createError && <div className="state error">Could not create mapping: {createError}</div>}
      {createSuccess && <div className="state success">{createSuccess}</div>}
    </section>
  );
}

function WeakMappingsTable({
  actionError,
  actionMappingId,
  mappings,
  onConfirm,
  onReject,
  resource,
}: {
  actionError: string | null;
  actionMappingId: number | null;
  mappings: WeakMapping[];
  onConfirm: (mappingId: number) => void;
  onReject: (mappingId: number) => void;
  resource: ResourceState<WeakMapping>;
}) {
  if (resource.loading) {
    return <div className="state">Loading weak mappings...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load weak mappings: {resource.error}</div>;
  }

  return (
    <section className="table-wrap" aria-label="Weak mappings">
      <table>
        <thead>
          <tr>
            <th>Product ID</th>
            <th>Product name</th>
            <th>Supplier</th>
            <th>Supplier SKU</th>
            <th>Supplier product</th>
            <th>Review reason</th>
            <th>Match status</th>
            <th>Match method</th>
            <th>Confidence</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {mappings.map((mapping) => (
            <tr
              className={mapping.match_status === "rejected" ? "row-rejected" : undefined}
              key={`${mapping.product_id}-${mapping.mapping_id ?? "unmapped"}`}
            >
              <td>{mapping.product_id}</td>
              <td>{mapping.product_name}</td>
              <td>{formatValue(mapping.supplier_name)}</td>
              <td>{formatValue(mapping.supplier_sku)}</td>
              <td>{formatValue(mapping.supplier_product_name)}</td>
              <td>
                <span className="review-need">{weakMappingReason(mapping)}</span>
              </td>
              <td>
                <span className={statusClassName(mapping.match_status)}>
                  {formatValue(mapping.match_status)}
                </span>
              </td>
              <td>{formatValue(mapping.match_method)}</td>
              <td>{formatValue(mapping.match_confidence)}</td>
              <td>
                {mapping.mapping_id ? (
                  <MappingActionButtons
                    isPreferred={false}
                    isRejected={mapping.match_status === "rejected"}
                    mappingId={mapping.mapping_id}
                    onConfirm={onConfirm}
                    onReject={onReject}
                    pending={actionMappingId === mapping.mapping_id}
                  />
                ) : (
                  "-"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {actionError && <div className="state error">Mapping action failed: {actionError}</div>}
      {mappings.length === 0 && <div className="state">No weak mappings found.</div>}
    </section>
  );
}

function SupplierMappingsTable({
  actionError,
  actionMappingId,
  mappings,
  onConfirm,
  onReject,
  onSetPreferred,
  onUnsetPreferred,
  resource,
}: {
  actionError: string | null;
  actionMappingId: number | null;
  mappings: ProductSupplierMapping[];
  onConfirm: (mappingId: number) => void;
  onReject: (mappingId: number) => void;
  onSetPreferred: (mappingId: number) => void;
  onUnsetPreferred: (mappingId: number) => void;
  resource: ResourceState<ProductSupplierMapping>;
}) {
  if (resource.loading) {
    return <div className="state">Loading supplier mappings...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load supplier mappings: {resource.error}</div>;
  }

  return (
    <section className="table-wrap" aria-label="Supplier mappings">
      <div className="state warning">
        Legacy ProductSupplier mappings are transitional. Active purchasing now uses the OrderPro
        supplier on each product.
      </div>
      <table>
        <thead>
          <tr>
            <th>Product name</th>
            <th>Supplier name</th>
            <th>Supplier SKU</th>
            <th>Supplier product</th>
            <th>Purchase price</th>
            <th>Match status</th>
            <th>Match method</th>
            <th>Preferred</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {mappings.map((mapping) => (
            <tr className={mapping.match_status === "rejected" ? "row-rejected" : undefined} key={mapping.id}>
              <td>{formatValue(mapping.product_name)}</td>
              <td>{formatValue(mapping.supplier_name)}</td>
              <td>{formatValue(mapping.supplier_sku)}</td>
              <td>{formatValue(mapping.supplier_product_name)}</td>
              <td>{formatPrice(mapping)}</td>
              <td>
                <span className={statusClassName(mapping.match_status)}>
                  {formatValue(mapping.match_status)}
                </span>
              </td>
              <td>{formatValue(mapping.match_method)}</td>
              <td>{formatBoolean(mapping.is_preferred)}</td>
              <td>
                <MappingActionButtons
                  isPreferred={mapping.is_preferred}
                  isRejected={mapping.match_status === "rejected"}
                  mappingId={mapping.id}
                  onConfirm={onConfirm}
                  onReject={onReject}
                  onSetPreferred={onSetPreferred}
                  onUnsetPreferred={onUnsetPreferred}
                  pending={actionMappingId === mapping.id}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {actionError && <div className="state error">Mapping action failed: {actionError}</div>}
      {mappings.length === 0 && <div className="state">No supplier mappings found.</div>}
    </section>
  );
}

function MappingActionButtons({
  isPreferred,
  isRejected,
  mappingId,
  onConfirm,
  onReject,
  onSetPreferred,
  onUnsetPreferred,
  pending,
}: {
  isPreferred: boolean;
  isRejected: boolean;
  mappingId: number;
  onConfirm: (mappingId: number) => void;
  onReject: (mappingId: number) => void;
  onSetPreferred?: (mappingId: number) => void;
  onUnsetPreferred?: (mappingId: number) => void;
  pending: boolean;
}) {
  return (
    <div className="action-row">
      <button disabled={pending || isRejected} onClick={() => onConfirm(mappingId)} type="button">
        Confirm
      </button>
      <button disabled={pending || isRejected} onClick={() => onReject(mappingId)} type="button">
        Reject
      </button>
      {onSetPreferred && onUnsetPreferred && (
        isPreferred ? (
          <button disabled={pending || isRejected} onClick={() => onUnsetPreferred(mappingId)} type="button">
            Unset Preferred
          </button>
        ) : (
          <button disabled={pending || isRejected} onClick={() => onSetPreferred(mappingId)} type="button">
            Set Preferred
          </button>
        )
      )}
      {pending && <span className="action-state">Working...</span>}
    </div>
  );
}

function ForecastPanel() {
  const [productIdInput, setProductIdInput] = useState("");
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const productId = Number(productIdInput);
    if (!Number.isInteger(productId) || productId <= 0) {
      setError("Enter a valid product ID.");
      setForecast(null);
      return;
    }

    setLoading(true);
    setError(null);

    fetchProductForecast(productId)
      .then((loadedForecast) => {
        setForecast(loadedForecast);
        setError(null);
      })
      .catch((loadError: Error) => {
        setForecast(null);
        setError(loadError.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }

  return (
    <section className="forecast-view" aria-label="Product forecast">
      <form className="forecast-form" onSubmit={handleSubmit}>
        <label className="search-label">
          <span>Product ID</span>
          <input
            inputMode="numeric"
            onChange={(event) => setProductIdInput(event.target.value)}
            placeholder="Enter product ID"
            value={productIdInput}
          />
        </label>
        <button type="submit">Fetch Forecast</button>
      </form>

      {!forecast && !loading && !error && (
        <div className="state">Enter a product ID to load a forecast.</div>
      )}
      {loading && <div className="state">Loading forecast...</div>}
      {error && <div className="state error">Could not load forecast: {error}</div>}
      {forecast && !loading && !error && <ForecastDetails forecast={forecast} />}
    </section>
  );
}

function ForecastDetails({ forecast }: { forecast: ForecastResponse }) {
  return (
    <div className="forecast-grid">
      <section className="detail-panel" aria-label="Forecast details">
        <h2>Forecast</h2>
        <dl className="detail-list">
          <div>
            <dt>Product</dt>
            <dd>
              {forecast.product_name} ({forecast.product_id})
            </dd>
          </div>
          <div>
            <dt>Current stock</dt>
            <dd>{formatValue(forecast.current_stock)}</dd>
          </div>
          <div>
            <dt>Inventory source</dt>
            <dd>{formatValue(forecast.inventory_source)}</dd>
          </div>
          <div>
            <dt>Average daily usage</dt>
            <dd>{formatValue(forecast.avg_daily_usage)}</dd>
          </div>
          <div>
            <dt>Days until stockout</dt>
            <dd>{formatValue(forecast.days_until_stockout)}</dd>
          </div>
          <div>
            <dt>Reorder point</dt>
            <dd>{formatValue(forecast.reorder_point)}</dd>
          </div>
          <div>
            <dt>Incoming stock</dt>
            <dd>{formatValue(forecast.incoming_qty)}</dd>
          </div>
          <div>
            <dt>Available for reorder</dt>
            <dd>{formatValue(forecast.effective_available_stock_for_reorder)}</dd>
          </div>
          <div>
            <dt>Recommended before inbound</dt>
            <dd>{formatValue(forecast.recommended_qty_before_inbound)}</dd>
          </div>
          <div>
            <dt>Recommended action</dt>
            <dd>{formatValue(forecast.recommended_action)}</dd>
          </div>
          <div>
            <dt>Recommended quantity</dt>
            <dd>{formatValue(forecast.recommended_qty)}</dd>
          </div>
          <div>
            <dt>Inbound adjustment</dt>
            <dd>{formatValue(forecast.inbound_adjustment_qty)}</dd>
          </div>
          <div>
            <dt>Risk level</dt>
            <dd>{formatValue(forecast.risk_level)}</dd>
          </div>
          <div>
            <dt>Explanation</dt>
            <dd>{formatValue(forecast.explanation)}</dd>
          </div>
        </dl>
      </section>

      <SupplierContextDetails context={forecast.supplier_context ?? null} />
      <ForecastInputDetails forecast={forecast} />
      <IncomingStockDetails context={forecast.incoming_stock_context ?? null} />
    </div>
  );
}

function ForecastInputDetails({ forecast }: { forecast: ForecastResponse }) {
  return (
    <section className="detail-panel" aria-label="Forecast input sources">
      <h2>Forecast Inputs</h2>
      <dl className="detail-list">
        <div>
          <dt>Estimated unit cost</dt>
          <dd>{formatValue(forecast.estimated_unit_cost)}</dd>
        </div>
        <div>
          <dt>Cost source</dt>
          <dd>{sourceLabel(forecast.estimated_cost_source ?? forecast.cost_source)}</dd>
        </div>
        <div>
          <dt>MOQ source</dt>
          <dd>{sourceLabel(forecast.moq_source)}</dd>
        </div>
        <div>
          <dt>Pack size</dt>
          <dd>{formatValue(forecast.pack_size)}</dd>
        </div>
        <div>
          <dt>Pack source</dt>
          <dd>{sourceLabel(forecast.pack_size_source)}</dd>
        </div>
        <div>
          <dt>Readiness score</dt>
          <dd>{formatValue(forecast.forecast_readiness_score)}</dd>
        </div>
        <div>
          <dt>Input warnings</dt>
          <dd>{(forecast.input_warning_issues ?? []).join(", ") || "-"}</dd>
        </div>
      </dl>
    </section>
  );
}

function IncomingStockDetails({ context }: { context: ForecastResponse["incoming_stock_context"] | null }) {
  if (!context) {
    return (
      <section className="detail-panel" aria-label="Incoming stock">
        <h2>Incoming Stock</h2>
        <div className="state">No incoming stock context returned.</div>
      </section>
    );
  }

  const localIncoming =
    context.incoming_qty_local ?? context.source_breakdown.local_purchase_orders?.incoming_qty ?? 0;
  const orderproIncoming =
    context.incoming_qty_orderpro ?? context.source_breakdown.orderpro_purchase_orders?.incoming_qty ?? 0;
  const totalIncoming = context.incoming_qty_total ?? context.incoming_qty;

  return (
    <section className="detail-panel" aria-label="Incoming stock">
      <h2>Incoming Stock</h2>
      <dl className="detail-list">
        <div>
          <dt>Total incoming</dt>
          <dd>{formatValue(totalIncoming)}</dd>
        </div>
        <div>
          <dt>Local incoming</dt>
          <dd>{formatValue(localIncoming)}</dd>
        </div>
        <div>
          <dt>OrderPro incoming</dt>
          <dd>{formatValue(orderproIncoming)}</dd>
        </div>
        <div>
          <dt>Open supplier POs</dt>
          <dd>{formatValue(context.open_po_count)}</dd>
        </div>
        <div>
          <dt>Open PO lines</dt>
          <dd>{formatValue(context.open_po_line_count)}</dd>
        </div>
        <div>
          <dt>Earliest expected</dt>
          <dd>{formatDate(context.earliest_expected_date)}</dd>
        </div>
        <div>
          <dt>Latest expected</dt>
          <dd>{formatDate(context.latest_expected_date)}</dd>
        </div>
      </dl>
      {context.warnings.length > 0 && (
        <ul className="warning-list">
          {context.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SupplierContextDetails({ context }: { context: ForecastSupplierContext | null }) {
  if (!context) {
    return (
      <section className="detail-panel" aria-label="Supplier context">
        <h2>Supplier Context</h2>
        <div className="state">No supplier context returned.</div>
      </section>
    );
  }

  return (
    <section className="detail-panel" aria-label="Supplier context">
      <h2>Supplier Context</h2>
      {context.needs_supplier_mapping && (
        <div className="state warning">
          This product needs supplier mapping before purchasing recommendations can be trusted.
        </div>
      )}
      <dl className="detail-list">
        <div>
          <dt>Selected supplier</dt>
          <dd>{formatValue(context.supplier_name)}</dd>
        </div>
        <div>
          <dt>Supplier ID</dt>
          <dd>{formatValue(context.supplier_id)}</dd>
        </div>
        <div>
          <dt>Supplier SKU</dt>
          <dd>{formatValue(context.supplier_sku)}</dd>
        </div>
        <div>
          <dt>Supplier product</dt>
          <dd>{formatValue(context.supplier_product_name)}</dd>
        </div>
        <div>
          <dt>Purchase price</dt>
          <dd>{formatPrice(context)}</dd>
        </div>
        <div>
          <dt>Lead time</dt>
          <dd>
            {formatValue(context.lead_time_days)} ({formatValue(context.lead_time_source)})
          </dd>
        </div>
        <div>
          <dt>MOQ</dt>
          <dd>
            {formatValue(context.minimum_order_quantity)} ({formatValue(context.moq_source)})
          </dd>
        </div>
        <div>
          <dt>Match status</dt>
          <dd>{formatValue(context.match_status)}</dd>
        </div>
        <div>
          <dt>Match method</dt>
          <dd>{formatValue(context.match_method)}</dd>
        </div>
        <div>
          <dt>Mapping source</dt>
          <dd>{mappingSourceLabel(context.mapping_source)}</dd>
        </div>
        <div>
          <dt>Has supplier mapping</dt>
          <dd>{formatBoolean(context.has_supplier_mapping)}</dd>
        </div>
        <div>
          <dt>Needs supplier mapping</dt>
          <dd>{formatBoolean(context.needs_supplier_mapping)}</dd>
        </div>
      </dl>
    </section>
  );
}

function RecommendationsPanel() {
  const [recommendations, setRecommendations] =
    useState<ResourceState<PurchaseRecommendation>>(initialResource);
  const [selectedRecommendation, setSelectedRecommendation] =
    useState<PurchaseRecommendation | null>(null);
  const [productId, setProductId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState(false);
  const [llmExplanation, setLlmExplanation] = useState<RecommendationLLMExplanation | null>(null);
  const [llmSuccess, setLlmSuccess] = useState<string | null>(null);

  const loadRecommendations = useCallback((active = true) => {
    listRecommendations()
      .then((loadedRecommendations) => {
        if (active) {
          setRecommendations({ data: loadedRecommendations, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setRecommendations({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  useEffect(() => {
    let active = true;
    loadRecommendations(active);
    return () => {
      active = false;
    };
  }, [loadRecommendations]);

  async function refreshSelected(recommendationId: number) {
    const loaded = await getRecommendation(recommendationId);
    setSelectedRecommendation(loaded);
    loadRecommendations();
  }

  async function handleSelect(recommendationId: number) {
    setActionError(null);
    setLlmSuccess(null);
    try {
      setLlmExplanation(null);
      await refreshSelected(recommendationId);
    } catch (loadError) {
      setActionError((loadError as Error).message);
    }
  }

  async function handleCreateRecommendation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedProductId = Number(productId);
    if (!Number.isInteger(parsedProductId) || parsedProductId <= 0) {
      setActionError("Product ID is required.");
      return;
    }

    setLoadingAction(true);
    setActionError(null);
    try {
      const created = await createReorderRecommendation(parsedProductId);
      setSelectedRecommendation(created);
      setLlmExplanation(null);
      setLlmSuccess(null);
      loadRecommendations();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLoadingAction(false);
    }
  }

  async function runRecommendationAction(action: () => Promise<PurchaseRecommendation>) {
    setLoadingAction(true);
    setActionError(null);
    try {
      const updated = await action();
      setSelectedRecommendation(updated);
      setLlmExplanation(null);
      setLlmSuccess(null);
      loadRecommendations();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLoadingAction(false);
    }
  }

  async function handleRejectRecommendation(recommendation: PurchaseRecommendation) {
    if (!window.confirm("Reject this recommendation?")) {
      return;
    }
    await runRecommendationAction(() =>
      rejectRecommendation(recommendation.id, {
        rejected_reason: rejectReason || null,
        reviewed_by: "manual",
      }),
    );
  }

  async function handleConvertRecommendation(recommendation: PurchaseRecommendation) {
    if (
      !window.confirm(
        "Convert this recommendation to a draft purchase order? This will not approve or issue it.",
      )
    ) {
      return;
    }
    setLoadingAction(true);
    setActionError(null);
    try {
      const converted = await convertRecommendationToDraftPO(recommendation.id);
      setSelectedRecommendation(converted.recommendation);
      setLlmExplanation(null);
      setLlmSuccess(null);
      loadRecommendations();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLoadingAction(false);
    }
  }

  async function handleGenerateLLMExplanation(recommendation: PurchaseRecommendation) {
    setLoadingAction(true);
    setActionError(null);
    setLlmSuccess(null);
    try {
      const explanation = await generateRecommendationLLMExplanation(recommendation.id);
      setLlmExplanation(explanation);
      setLlmSuccess("AI explanation generated.");
      await refreshSelected(recommendation.id);
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLoadingAction(false);
    }
  }

  return (
    <div className="review-stack">
      <section className="detail-panel" aria-label="Create recommendation">
        <h2>Generate Reorder Recommendation</h2>
        <div className="state">
          Recommendations are advisory. Converting a recommendation only creates a draft purchase
          order. It does not approve or issue it.
        </div>
        <form className="mapping-form" onSubmit={handleCreateRecommendation}>
          <label>
            <span>Product ID</span>
            <input onChange={(event) => setProductId(event.target.value)} value={productId} />
          </label>
          <button disabled={loadingAction} type="submit">
            Generate Reorder Recommendation
          </button>
        </form>
        {actionError && <div className="state error">Recommendation action failed: {actionError}</div>}
      </section>

      <RecommendationsTable
        onSelect={handleSelect}
        recommendations={recommendations.data}
        resource={recommendations}
        selectedRecommendationId={selectedRecommendation?.id ?? null}
      />

      {selectedRecommendation ? (
        <RecommendationDetail
          loadingAction={loadingAction}
          onAccept={(recommendation) =>
            runRecommendationAction(() =>
              acceptRecommendation(recommendation.id, { reviewed_by: "manual" }),
            )
          }
          onConvert={handleConvertRecommendation}
          onGenerateLLMExplanation={handleGenerateLLMExplanation}
          onReject={handleRejectRecommendation}
          recommendation={selectedRecommendation}
          llmExplanation={llmExplanation}
          llmSuccess={llmSuccess}
          rejectReason={rejectReason}
          onRejectReasonChange={setRejectReason}
        />
      ) : (
        <div className="state">Select a recommendation to view details.</div>
      )}
    </div>
  );
}

function RecommendationsTable({
  onSelect,
  recommendations,
  resource,
  selectedRecommendationId,
}: {
  onSelect: (recommendationId: number) => void;
  recommendations: PurchaseRecommendation[];
  resource: ResourceState<PurchaseRecommendation>;
  selectedRecommendationId: number | null;
}) {
  if (resource.loading) {
    return <div className="state">Loading recommendations...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load recommendations: {resource.error}</div>;
  }

  return (
    <section className="table-wrap" aria-label="Recommendations list">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Product</th>
            <th>Supplier</th>
            <th>Qty</th>
            <th>Unit cost</th>
            <th>Total</th>
            <th>Currency</th>
            <th>Confidence</th>
            <th>Status</th>
            <th>Generated by</th>
            <th>Created</th>
            <th>Converted PO</th>
            <th>View</th>
          </tr>
        </thead>
        <tbody>
          {recommendations.map((recommendation) => (
            <tr key={recommendation.id}>
              <td>{recommendation.id}</td>
              <td>
                {recommendation.product_name ?? "-"} ({recommendation.product_id})
              </td>
              <td>{formatValue(recommendation.supplier_name)}</td>
              <td>{formatValue(recommendation.recommended_quantity)}</td>
              <td>{formatValue(recommendation.estimated_unit_cost)}</td>
              <td>{formatValue(recommendation.estimated_total_cost)}</td>
              <td>{formatValue(recommendation.currency)}</td>
              <td>{formatValue(recommendation.confidence)}</td>
              <td>
                <span className={recommendationStatusClassName(recommendation.status)}>
                  {recommendation.status}
                </span>
              </td>
              <td>{formatValue(recommendation.generated_by)}</td>
              <td>{formatDate(recommendation.created_at)}</td>
              <td>{formatValue(recommendation.converted_purchase_order_id)}</td>
              <td>
                <button onClick={() => onSelect(recommendation.id)} type="button">
                  {selectedRecommendationId === recommendation.id ? "Viewing" : "View"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {recommendations.length === 0 && <div className="state">No recommendations found.</div>}
    </section>
  );
}

function RecommendationDetail({
  loadingAction,
  llmExplanation,
  llmSuccess,
  onAccept,
  onConvert,
  onGenerateLLMExplanation,
  onReject,
  onRejectReasonChange,
  recommendation,
  rejectReason,
}: {
  loadingAction: boolean;
  llmExplanation: RecommendationLLMExplanation | null;
  llmSuccess: string | null;
  onAccept: (recommendation: PurchaseRecommendation) => void;
  onConvert: (recommendation: PurchaseRecommendation) => void;
  onGenerateLLMExplanation: (recommendation: PurchaseRecommendation) => void;
  onReject: (recommendation: PurchaseRecommendation) => void;
  onRejectReasonChange: (value: string) => void;
  recommendation: PurchaseRecommendation;
  rejectReason: string;
}) {
  const canAccept = recommendation.status === "pending_review" || recommendation.status === "draft";
  const canReject = recommendation.status !== "rejected" && recommendation.status !== "converted_to_po";
  const canConvert = recommendation.status === "accepted";
  const supplierSnapshot = recommendation.supplier_context_snapshot;
  const forecastSnapshot = recommendation.forecast_snapshot;

  return (
    <section className="detail-panel" aria-label="Recommendation details">
      <div className="section-header">
        <h2>Recommendation {recommendation.id}</h2>
        <div className="action-row">
          <button
            disabled={loadingAction}
            onClick={() => onGenerateLLMExplanation(recommendation)}
            type="button"
          >
            {loadingAction ? "Generating AI Explanation..." : "Generate AI Explanation"}
          </button>
          {canAccept && (
            <button disabled={loadingAction} onClick={() => onAccept(recommendation)} type="button">
              Accept
            </button>
          )}
          {canReject && (
            <>
              <input
                aria-label="Reject reason"
                onChange={(event) => onRejectReasonChange(event.target.value)}
                placeholder="Reject reason"
                value={rejectReason}
              />
              <button disabled={loadingAction} onClick={() => onReject(recommendation)} type="button">
                Reject
              </button>
            </>
          )}
          {canConvert && (
            <button disabled={loadingAction} onClick={() => onConvert(recommendation)} type="button">
              Convert to Draft PO
            </button>
          )}
        </div>
      </div>
      <div className="state warning">
        Advisory only. Draft purchase orders still require human approval before issuing.
      </div>
      <section className="nested-panel" aria-label="AI explanation">
        <h3>AI Explanation</h3>
        <div className="state warning">
          AI explanations are advisory only. They do not approve, issue, or place purchase orders.
        </div>
        {llmSuccess && <div className="state success">{llmSuccess}</div>}
        {llmExplanation ? (
          <dl className="detail-list">
            <div>
              <dt>Suggested action</dt>
              <dd>{formatValue(llmExplanation.suggested_action)}</dd>
            </div>
            <div>
              <dt>Summary</dt>
              <dd>{formatValue(llmExplanation.summary)}</dd>
            </div>
            <div>
              <dt>Explanation</dt>
              <dd>{formatValue(llmExplanation.explanation)}</dd>
            </div>
            <div>
              <dt>Risk flags</dt>
              <dd>{llmExplanation.risk_flags.length ? llmExplanation.risk_flags.join(", ") : "-"}</dd>
            </div>
            <div>
              <dt>Missing data warnings</dt>
              <dd>
                {llmExplanation.missing_data_warnings.length
                  ? llmExplanation.missing_data_warnings.join(", ")
                  : "-"}
              </dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{formatValue(llmExplanation.confidence)}</dd>
            </div>
            <div>
              <dt>Structured data citations</dt>
              <dd>
                {llmExplanation.structured_data_citations.length
                  ? llmExplanation.structured_data_citations.join(", ")
                  : "-"}
              </dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{formatValue(llmExplanation.model_name)}</dd>
            </div>
            <div>
              <dt>Prompt version</dt>
              <dd>{formatValue(llmExplanation.prompt_version)}</dd>
            </div>
          </dl>
        ) : (
          <div className="state">No AI explanation generated yet.</div>
        )}
      </section>
      <dl className="detail-list">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={recommendationStatusClassName(recommendation.status)}>
              {recommendation.status}
            </span>
          </dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{formatValue(recommendation.reason)}</dd>
        </div>
        <div>
          <dt>Recommended quantity</dt>
          <dd>{formatValue(recommendation.recommended_quantity)}</dd>
        </div>
        <div>
          <dt>Estimated cost</dt>
          <dd>
            {formatValue(recommendation.estimated_total_cost)} {formatValue(recommendation.currency)}
          </dd>
        </div>
      </dl>

      <section className="nested-panel" aria-label="Recommendation supplier snapshot">
        <h3>Supplier Context Snapshot</h3>
        <dl className="detail-list">
          <div>
            <dt>Supplier</dt>
            <dd>{snapshotValue(supplierSnapshot, "supplier_name")}</dd>
          </div>
          <div>
            <dt>Supplier SKU</dt>
            <dd>{snapshotValue(supplierSnapshot, "supplier_sku")}</dd>
          </div>
          <div>
            <dt>Supplier product</dt>
            <dd>{snapshotValue(supplierSnapshot, "supplier_product_name")}</dd>
          </div>
          <div>
            <dt>Mapping source</dt>
            <dd>{snapshotValue(supplierSnapshot, "mapping_source")}</dd>
          </div>
          <div>
            <dt>Lead time</dt>
            <dd>{snapshotValue(supplierSnapshot, "lead_time_days")}</dd>
          </div>
          <div>
            <dt>MOQ</dt>
            <dd>{snapshotValue(supplierSnapshot, "minimum_order_quantity")}</dd>
          </div>
          <div>
            <dt>Purchase price</dt>
            <dd>{snapshotValue(supplierSnapshot, "purchase_price")}</dd>
          </div>
        </dl>
      </section>

      <section className="nested-panel" aria-label="Recommendation forecast snapshot">
        <h3>Forecast Snapshot</h3>
        <dl className="detail-list">
          <div>
            <dt>Recommended action</dt>
            <dd>{snapshotValue(forecastSnapshot, "recommended_action")}</dd>
          </div>
          <div>
            <dt>Risk level</dt>
            <dd>{snapshotValue(forecastSnapshot, "risk_level")}</dd>
          </div>
          <div>
            <dt>Reorder point</dt>
            <dd>{snapshotValue(forecastSnapshot, "reorder_point")}</dd>
          </div>
          <div>
            <dt>Incoming stock</dt>
            <dd>{snapshotValue(forecastSnapshot, "incoming_qty")}</dd>
          </div>
          <div>
            <dt>Recommended before inbound</dt>
            <dd>{snapshotValue(forecastSnapshot, "recommended_qty_before_inbound")}</dd>
          </div>
          <div>
            <dt>Recommended after inbound</dt>
            <dd>{snapshotValue(forecastSnapshot, "recommended_qty_after_inbound")}</dd>
          </div>
          <div>
            <dt>Explanation</dt>
            <dd>{snapshotValue(forecastSnapshot, "explanation")}</dd>
          </div>
        </dl>
      </section>
    </section>
  );
}

function SupplierForecastPanel({ onViewPurchaseOrder }: { onViewPurchaseOrder: (poId: number) => void }) {
  const [supplierId, setSupplierId] = useState("");
  const [forecast, setForecast] = useState<SupplierForecastResponse | null>(null);
  const [filter, setFilter] = useState<SupplierForecastFilter>("all");
  const [draftNotes, setDraftNotes] = useState("Draft generated from supplier forecast");
  const [draftResult, setDraftResult] = useState<DraftFromProductsResponse | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedSupplierId = Number(supplierId);
    if (!Number.isInteger(parsedSupplierId) || parsedSupplierId <= 0) {
      setError("Supplier ID is required.");
      return;
    }

    setLoading(true);
    setError(null);
    setForecast(null);
    setDraftResult(null);
    setDraftError(null);
    try {
      setForecast(await getSupplierForecast(parsedSupplierId));
    } catch (loadError) {
      setError((loadError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateDraftFromForecast() {
    if (!forecast) {
      return;
    }
    if (
      !window.confirm(
        "Generate a draft PO from this supplier forecast? Only products with recommended quantity greater than zero will be included. This creates a draft only; it will not be approved, issued, or sent to OrderPro.",
      )
    ) {
      return;
    }

    setGeneratingDraft(true);
    setDraftError(null);
    setDraftResult(null);
    try {
      const created = await createDraftPOFromSupplierForecast(forecast.supplier_id, {
        created_by: "manual",
        notes: draftNotes || "Draft generated from supplier forecast",
        only_reorder_needed: true,
      });
      setDraftResult(created);
    } catch (loadError) {
      setDraftError((loadError as Error).message);
    } finally {
      setGeneratingDraft(false);
    }
  }

  const sortedRows = useMemo(
    () => sortSupplierForecastRows(forecast?.forecasts ?? []),
    [forecast],
  );
  const visibleRows = useMemo(
    () => sortedRows.filter((row) => forecastMatchesFilter(row, filter)),
    [filter, sortedRows],
  );

  const highRiskCount = (forecast?.forecasts ?? []).filter(
    (row) => row.risk_level === "high" || row.risk_level === "critical",
  ).length;
  const openDemandCount = (forecast?.forecasts ?? []).filter(forecastHasOpenDemand).length;
  const missingLeadTimeCount = (forecast?.forecasts ?? []).filter(forecastMissingLeadTime).length;
  const noHistoryCount = (forecast?.forecasts ?? []).filter(forecastHasNoDemandHistory).length;

  return (
    <section className="detail-panel" aria-label="Supplier forecast">
      <h2>Supplier Forecast</h2>
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Supplier ID</span>
          <input onChange={(event) => setSupplierId(event.target.value)} value={supplierId} />
        </label>
        <button disabled={loading} type="submit">
          {loading ? "Loading..." : "Load Supplier Forecast"}
        </button>
      </form>
      {error && <div className="state error">Supplier forecast failed: {error}</div>}
      {!forecast && !loading && !error && (
        <div className="state">Enter a supplier ID to review OrderPro product forecasts.</div>
      )}
      {forecast && (
        <div className="review-stack">
          <div className="state">
            Forecasts use synced OrderPro inventory and order history. Draft generation does not
            approve, issue, or send purchase orders.
          </div>
          <dl className="detail-list">
            <div>
              <dt>Supplier</dt>
              <dd>{formatValue(forecast.supplier_name)}</dd>
            </div>
            <div>
              <dt>Product count</dt>
              <dd>{forecast.product_count}</dd>
            </div>
            <div>
              <dt>Products needing reorder</dt>
              <dd>{forecast.products_needing_reorder.length}</dd>
            </div>
            <div>
              <dt>High-risk products</dt>
              <dd>{highRiskCount}</dd>
            </div>
            <div>
              <dt>Products with open demand</dt>
              <dd>{openDemandCount}</dd>
            </div>
            <div>
              <dt>Missing lead time</dt>
              <dd>{missingLeadTimeCount}</dd>
            </div>
            <div>
              <dt>No usable demand history</dt>
              <dd>{noHistoryCount}</dd>
            </div>
            <div>
              <dt>Total recommended quantity</dt>
              <dd>{forecast.total_recommended_quantity}</dd>
            </div>
            <div>
              <dt>Total estimated cost</dt>
              <dd>{formatValue(forecast.total_estimated_cost)}</dd>
            </div>
          </dl>
          <section className="nested-panel" aria-label="Generate supplier forecast draft PO">
            <div className="section-header">
              <h3>Generate PO from supplier forecast</h3>
              <span className="status needs-review">draft only</span>
            </div>
            <div className="state">
              Only products with recommended quantity greater than zero will be included. The result
              is a draft PO only; it will not be approved, issued, or sent to OrderPro.
            </div>
            <form
              className="mapping-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleGenerateDraftFromForecast();
              }}
            >
              <label>
                <span>Notes</span>
                <input
                  onChange={(event) => setDraftNotes(event.target.value)}
                  value={draftNotes}
                />
              </label>
              <button
                disabled={generatingDraft || forecast.products_needing_reorder.length === 0}
                type="submit"
              >
                {generatingDraft ? "Generating..." : "Generate Draft PO from Supplier Forecast"}
              </button>
            </form>
            {forecast.products_needing_reorder.length === 0 && (
              <div className="action-state">No products currently require reorder.</div>
            )}
            {draftError && (
              <div className="state error">Supplier forecast draft generation failed: {draftError}</div>
            )}
            {draftResult && (
              <DraftPoGenerationResult
                onViewPurchaseOrder={onViewPurchaseOrder}
                result={draftResult}
              />
            )}
          </section>
          {forecast.products_needing_reorder.length === 0 && (
            <div className="state">No products need reorder for this supplier.</div>
          )}
          {noHistoryCount > 0 && (
            <div className="state warning">
              Some products have no usable demand history and are being monitored.
            </div>
          )}
          {missingLeadTimeCount > 0 && (
            <div className="state warning">
              Some products are missing lead time, so their recommendations need review.
            </div>
          )}
          <div className="filter-bar" role="group" aria-label="Supplier forecast filters">
            {[
              ["all", "All products"],
              ["needs_reorder", "Needs reorder"],
              ["high_risk", "High risk"],
              ["open_demand", "Open demand"],
              ["no_history", "No demand history"],
              ["missing_lead_time", "Missing lead time"],
            ].map(([value, label]) => (
              <button
                className={filter === value ? "tab active" : "tab"}
                key={value}
                onClick={() => setFilter(value as SupplierForecastFilter)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <section className="table-wrap nested-table" aria-label="Supplier forecast rows">
            <table>
              <thead>
                <tr>
                  <th>Product ID</th>
                  <th>OrderPro SKU</th>
                  <th>Product name</th>
                  <th>Current stock</th>
                  <th>Effective stock</th>
                  <th>Shipped units</th>
                  <th>Avg daily usage</th>
                  <th>Open confirmed</th>
                  <th>Open packed</th>
                  <th>Open backorder</th>
                  <th>Total open</th>
                  <th>Incoming</th>
                  <th>Lead time</th>
                  <th>Reorder point</th>
                  <th>Before inbound</th>
                  <th>Recommended qty</th>
                  <th>Action</th>
                  <th>Risk level</th>
                  <th>Demand source</th>
                  <th>Explanation</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.product_id}>
                    <td>{row.product_id}</td>
                    <td>{formatValue(row.orderpro_sku)}</td>
                    <td>{row.product_name}</td>
                    <td>{formatValue(row.current_stock)}</td>
                    <td>{formatValue(row.effective_available_stock)}</td>
                    <td>{formatValue(row.shipped_units_in_window)}</td>
                    <td>{formatValue(row.avg_daily_usage)}</td>
                    <td>{formatValue(row.open_confirmed_units)}</td>
                    <td>{formatValue(row.open_packed_units)}</td>
                    <td>{formatValue(row.open_backorder_units)}</td>
                    <td>{formatValue(row.total_open_demand)}</td>
                    <td>{formatValue(row.incoming_qty)}</td>
                    <td>
                      {formatValue(row.lead_time_days_used)} ({formatValue(row.lead_time_source)})
                    </td>
                    <td>{formatValue(row.reorder_point)}</td>
                    <td>{formatValue(row.recommended_qty_before_inbound)}</td>
                    <td>{formatValue(row.recommended_qty)}</td>
                    <td>{row.recommended_action}</td>
                    <td>
                      <span className={forecastRiskClassName(row.risk_level)}>
                        {row.risk_level}
                      </span>
                    </td>
                    <td>{demandSourceLabel(row.demand_source)}</td>
                    <td>{formatValue(row.explanation)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {forecast.forecasts.length === 0 && (
              <div className="state">No active products found for this supplier.</div>
            )}
            {forecast.forecasts.length > 0 && visibleRows.length === 0 && (
              <div className="state">No products match this forecast filter.</div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

type ForecastReadinessFilter =
  | "all"
  | "missing_supplier"
  | "missing_cost"
  | "missing_lead_time"
  | "missing_moq"
  | "missing_pack_size"
  | "fallback_moq"
  | "po_derived_cost"
  | "ready_for_forecast";

const forecastReadinessFilters: Array<{ value: ForecastReadinessFilter; label: string }> = [
  { value: "all", label: "All products" },
  { value: "missing_supplier", label: "Missing supplier" },
  { value: "missing_cost", label: "Missing cost" },
  { value: "missing_lead_time", label: "Missing lead time" },
  { value: "missing_moq", label: "Missing MOQ" },
  { value: "missing_pack_size", label: "Missing pack size" },
  { value: "fallback_moq", label: "Fallback MOQ" },
  { value: "po_derived_cost", label: "PO-derived cost" },
  { value: "ready_for_forecast", label: "Ready for forecast" },
];

function sourceLabel(source: string | null | undefined): string {
  const labels: Record<string, string> = {
    orderpro_product_cost: "OrderPro product cost",
    orderpro_purchase_order_line: "OrderPro PO line",
    local_purchase_order_line: "Local PO line",
    product_record: "Product record",
    supplier_record: "Supplier record",
    legacy_product_supplier: "Legacy mapping",
    business_default: "Business default",
    missing: "Missing",
  };
  return source ? labels[source] ?? source : "-";
}

type SupplierAssignmentFilter = "all" | "high" | "medium" | "low" | "none";
type SupplierAssignmentStatusFilter = "all" | "suggested" | "no_evidence" | "confirmed" | "rejected";

function SupplierAssignmentReviewPanel() {
  const [summary, setSummary] = useState<SupplierAssignmentReviewSummary | null>(null);
  const [rows, setRows] = useState<ResourceState<SupplierAssignmentReviewItem>>(initialResource);
  const [suppliers, setSuppliers] = useState<SupplierOption[]>([]);
  const [confidenceFilter, setConfidenceFilter] = useState<SupplierAssignmentFilter>("all");
  const [statusFilter, setStatusFilter] = useState<SupplierAssignmentStatusFilter>("all");
  const [hasDemandOnly, setHasDemandOnly] = useState(false);
  const [hasOpenDemandOnly, setHasOpenDemandOnly] = useState(false);
  const [manualSupplierByProduct, setManualSupplierByProduct] = useState<Record<number, string>>({});
  const [actionProductId, setActionProductId] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadReview = useCallback(
    (active = true) => {
      setRows((current) => ({ ...current, loading: true, error: null }));
      setActionError(null);
      Promise.all([
        getSupplierAssignmentReviewSummary(),
        getSupplierAssignmentReviewItems({
          confidence: confidenceFilter === "all" ? undefined : confidenceFilter,
          status: statusFilter === "all" ? undefined : statusFilter,
          has_demand: hasDemandOnly ? true : undefined,
          has_open_demand: hasOpenDemandOnly ? true : undefined,
        }),
        listSuppliers(),
      ])
        .then(([loadedSummary, loadedRows, loadedSuppliers]) => {
          if (active) {
            setSummary(loadedSummary);
            setRows({ data: loadedRows, loading: false, error: null });
            setSuppliers(loadedSuppliers);
          }
        })
        .catch((error: Error) => {
          if (active) {
            setRows({ data: [], loading: false, error: error.message });
          }
        });
    },
    [confidenceFilter, hasDemandOnly, hasOpenDemandOnly, statusFilter],
  );

  useEffect(() => {
    let active = true;
    loadReview(active);
    return () => {
      active = false;
    };
  }, [loadReview]);

  async function runReviewAction(
    productId: number,
    action: () => Promise<unknown>,
    message: string,
  ) {
    setActionProductId(productId);
    setActionError(null);
    setActionMessage(null);
    try {
      await action();
      setActionMessage(message);
      loadReview();
    } catch (error) {
      setActionError((error as Error).message);
    } finally {
      setActionProductId(null);
    }
  }

  function confirmSuggestion(row: SupplierAssignmentReviewItem) {
    if (!row.suggested_supplier_id) {
      setActionError("No suggested supplier is available for this product.");
      return;
    }
    void runReviewAction(
      row.product_id,
      () =>
        confirmSupplierAssignmentReview(row.product_id, {
          supplier_id: row.suggested_supplier_id as number,
          reviewed_by: "manual",
          note: "Confirmed from supplier assignment review.",
        }),
      "Supplier assignment confirmed locally.",
    );
  }

  function rejectSuggestion(row: SupplierAssignmentReviewItem) {
    if (!window.confirm("Reject this supplier assignment suggestion?")) {
      return;
    }
    void runReviewAction(
      row.product_id,
      () =>
        rejectSupplierAssignmentReview(row.product_id, {
          reviewed_by: "manual",
          reason: "Rejected from supplier assignment review.",
        }),
      "Supplier assignment suggestion rejected.",
    );
  }

  function confirmManualSupplier(row: SupplierAssignmentReviewItem) {
    const selectedSupplierId = Number(manualSupplierByProduct[row.product_id] || 0);
    if (!selectedSupplierId) {
      setActionError("Choose a supplier before confirming manually.");
      return;
    }
    void runReviewAction(
      row.product_id,
      () =>
        confirmSupplierAssignmentReview(row.product_id, {
          supplier_id: selectedSupplierId,
          reviewed_by: "manual",
          note: "Manually selected supplier from review workflow.",
        }),
      "Manual supplier assignment confirmed locally.",
    );
  }

  return (
    <div className="review-stack" aria-label="Supplier assignment review workspace">
      <section className="panel-heading">
        <div>
          <h2>Supplier Assignment Review</h2>
          <p>
            Review missing product suppliers using deterministic evidence. Confirmations are local only and are not pushed to OrderPro.
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => loadReview()}>
          Refresh
        </button>
      </section>

      {summary && (
        <section className="summary-grid" aria-label="Supplier assignment summary">
          <SummaryCard label="Missing supplier" value={summary.missing_supplier_products} />
          <SummaryCard label="With stock" value={summary.missing_supplier_products_with_stock} />
          <SummaryCard label="With demand" value={summary.missing_supplier_products_with_demand_history} />
          <SummaryCard label="With open demand" value={summary.missing_supplier_products_with_open_customer_demand} />
          <SummaryCard label="PO evidence" value={summary.missing_supplier_products_with_po_supplier_evidence} />
          <SummaryCard label="No evidence" value={summary.missing_supplier_products_with_no_evidence} />
          <SummaryCard label="High confidence" value={summary.suggested_supplier_count_by_confidence.high ?? 0} />
          <SummaryCard label="Medium confidence" value={summary.suggested_supplier_count_by_confidence.medium ?? 0} />
        </section>
      )}

      <section className="detail-panel" aria-label="Supplier assignment filters">
        <div className="filter-grid">
          <label>
            Confidence
            <select
              value={confidenceFilter}
              onChange={(event) => setConfidenceFilter(event.target.value as SupplierAssignmentFilter)}
            >
              <option value="all">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="none">No evidence</option>
            </select>
          </label>
          <label>
            Status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as SupplierAssignmentStatusFilter)}
            >
              <option value="all">All</option>
              <option value="suggested">Suggested</option>
              <option value="no_evidence">No evidence</option>
              <option value="confirmed">Confirmed</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="checkbox-label">
            <input
              checked={hasDemandOnly}
              onChange={(event) => setHasDemandOnly(event.target.checked)}
              type="checkbox"
            />
            Has demand
          </label>
          <label className="checkbox-label">
            <input
              checked={hasOpenDemandOnly}
              onChange={(event) => setHasOpenDemandOnly(event.target.checked)}
              type="checkbox"
            />
            Has open demand
          </label>
        </div>
      </section>

      {actionMessage && <p className="success-state">{actionMessage}</p>}
      {actionError && <p className="error-state">{actionError}</p>}

      <section className="table-wrap" aria-label="Supplier assignment review rows">
        {rows.loading && <p className="empty-state">Loading supplier assignment review...</p>}
        {rows.error && <p className="error-state">{rows.error}</p>}
        {!rows.loading && !rows.error && rows.data.length === 0 && (
          <p className="empty-state">No missing-supplier products match these filters.</p>
        )}
        {!rows.loading && !rows.error && rows.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>SKU</th>
                <th>Stock</th>
                <th>Demand</th>
                <th>Suggested supplier</th>
                <th>Confidence</th>
                <th>Evidence</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((row) => (
                <tr key={row.product_id}>
                  <td>
                    <strong>{row.name}</strong>
                    <div className="muted">
                      ID {row.product_id} | {formatValue(row.brand)} | {formatValue(row.category)}
                    </div>
                  </td>
                  <td>{formatValue(row.orderpro_sku)}</td>
                  <td>{formatValue(row.current_stock)}</td>
                  <td>
                    <div>{row.demand_history_available ? "Has demand" : "No demand history"}</div>
                    <div className="muted">Open: {formatValue(row.open_customer_demand)}</div>
                  </td>
                  <td>{formatValue(row.suggested_supplier_name)}</td>
                  <td>
                    <span className={statusClassName(row.confidence_label)}>
                      {row.confidence_label}
                    </span>
                    <div className="muted">{formatValue(row.confidence_score)}</div>
                  </td>
                  <td>
                    <div>{formatValue(row.suggestion_source)}</div>
                    <div className="muted">
                      {formatValue(
                        typeof row.evidence_summary?.message === "string"
                          ? row.evidence_summary.message
                          : row.evidence_date,
                      )}
                    </div>
                    {row.warnings.map((warning) => (
                      <div className="muted" key={warning}>{warning}</div>
                    ))}
                  </td>
                  <td>
                    <span className={statusClassName(row.status)}>{row.status}</span>
                  </td>
                  <td>
                    <div className="action-stack">
                      <button
                        disabled={!row.suggested_supplier_id || actionProductId === row.product_id}
                        onClick={() => confirmSuggestion(row)}
                        type="button"
                      >
                        Confirm suggestion
                      </button>
                      <button
                        disabled={actionProductId === row.product_id}
                        onClick={() => rejectSuggestion(row)}
                        type="button"
                      >
                        Reject suggestion
                      </button>
                      <label>
                        Choose supplier manually
                        <select
                          aria-label={`Manual supplier for ${row.name}`}
                          value={manualSupplierByProduct[row.product_id] ?? ""}
                          onChange={(event) =>
                            setManualSupplierByProduct((current) => ({
                              ...current,
                              [row.product_id]: event.target.value,
                            }))
                          }
                        >
                          <option value="">Select supplier</option>
                          {suppliers.map((supplier) => (
                            <option key={supplier.id} value={supplier.id}>
                              {supplier.name} {supplier.orderpro_code ? `(${supplier.orderpro_code})` : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        disabled={actionProductId === row.product_id}
                        onClick={() => confirmManualSupplier(row)}
                        type="button"
                      >
                        Confirm manual supplier
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function ForecastReadinessPanel() {
  const [summary, setSummary] = useState<ForecastReadinessSummary | null>(null);
  const [rows, setRows] = useState<ResourceState<ForecastInputAudit>>(initialResource);
  const [filter, setFilter] = useState<ForecastReadinessFilter>("all");

  const loadReadiness = useCallback(
    (active = true) => {
      setRows((current) => ({ ...current, loading: true, error: null }));
      Promise.all([
        getForecastReadinessSummary(),
        getForecastReadinessRows(filter),
      ])
        .then(([loadedSummary, loadedRows]) => {
          if (active) {
            setSummary(loadedSummary);
            setRows({ data: loadedRows, loading: false, error: null });
          }
        })
        .catch((error: Error) => {
          if (active) {
            setRows({ data: [], loading: false, error: error.message });
          }
        });
    },
    [filter],
  );

  useEffect(() => {
    let active = true;
    loadReadiness(active);
    return () => {
      active = false;
    };
  }, [loadReadiness]);

  return (
    <div className="review-stack" aria-label="Forecast readiness workspace">
      <section className="panel-heading">
        <div>
          <h2>Forecast Readiness</h2>
          <p>
            Deterministic reconciliation only. These inputs explain forecast quality and do not activate seasonality.
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => loadReadiness()}>
          Refresh
        </button>
      </section>

      {summary && (
        <section className="summary-grid" aria-label="Forecast readiness summary">
          <SummaryCard label="OrderPro products" value={summary.product_count} />
          <SummaryCard label="Complete before reconciliation" value={summary.products_complete_before_reconciliation ?? "-"} />
          <SummaryCard label="Complete after reconciliation" value={summary.products_complete_after_reconciliation ?? summary.products_with_complete_critical_inputs} />
          <SummaryCard label="Missing supplier" value={summary.products_missing_supplier} />
          <SummaryCard label="Missing cost" value={summary.products_missing_cost} />
          <SummaryCard label="Missing lead time" value={summary.products_missing_lead_time} />
          <SummaryCard label="Fallback MOQ" value={summary.products_using_fallback_moq ?? "-"} />
          <SummaryCard label="PO-derived cost" value={summary.products_using_po_derived_cost ?? "-"} />
        </section>
      )}

      <section className="detail-panel" aria-label="Forecast readiness filters">
        <div className="filter-row">
          {forecastReadinessFilters.map((option) => (
            <button
              key={option.value}
              className={filter === option.value ? "filter-chip active" : "filter-chip"}
              type="button"
              onClick={() => setFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      <section className="table-wrap" aria-label="Forecast readiness rows">
        {rows.loading && <p className="empty-state">Loading forecast readiness...</p>}
        {rows.error && <p className="error-state">{rows.error}</p>}
        {!rows.loading && !rows.error && rows.data.length === 0 && (
          <p className="empty-state">No products match this readiness filter.</p>
        )}
        {!rows.loading && !rows.error && rows.data.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>SKU</th>
                <th>Cost</th>
                <th>Lead time</th>
                <th>MOQ</th>
                <th>Pack</th>
                <th>Readiness</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((row) => (
                <tr key={row.product_id}>
                  <td>{row.product_name}</td>
                  <td>{formatValue(row.orderpro_sku)}</td>
                  <td>
                    <strong>{formatValue(row.cost_price)}</strong>
                    <span className="muted"> {sourceLabel(row.cost_source)}</span>
                  </td>
                  <td>
                    <strong>{formatValue(row.lead_time_days)}</strong>
                    <span className="muted"> {sourceLabel(row.lead_time_source)}</span>
                  </td>
                  <td>
                    <strong>{formatValue(row.min_order_qty)}</strong>
                    <span className="muted"> {sourceLabel(row.moq_source)}</span>
                  </td>
                  <td>
                    <strong>{formatValue(row.pack_size)}</strong>
                    <span className="muted"> {sourceLabel(row.pack_size_source)}</span>
                  </td>
                  <td>{formatValue(row.forecast_readiness_score ?? row.readiness_score)}</td>
                  <td>
                    {[...(row.blocking_issues ?? []), ...(row.warning_issues ?? [])].map((issue) => (
                      <span key={issue} className={issue.startsWith("missing_supplier") ? "status rejected" : "status needs-review"}>
                        {issue}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function SeasonalityPanel() {
  const currentMonth = new Date().getMonth() + 1;
  const [month, setMonth] = useState(currentMonth);
  const [statusFilter, setStatusFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [stockFilter, setStockFilter] = useState("all");
  const [supplierAssignmentFilter, setSupplierAssignmentFilter] = useState("all");
  const [quickFilter, setQuickFilter] = useState("none");
  const [sortBy, setSortBy] = useState("seasonal_index");
  const [summary, setSummary] = useState<SeasonalitySummary | null>(null);
  const [products, setProducts] = useState<ResourceState<SeasonalProduct>>(initialResource);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<SeasonalProduct | null>(null);
  const [detail, setDetail] = useState<ProductSeasonalityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState<string | null>(null);

  const loadSeasonality = useCallback(
    (active = true) => {
      setProducts((current) => ({ ...current, loading: true, error: null }));
      setSummaryError(null);
      Promise.all([
        getSeasonalitySummary(month),
        getSeasonalProducts({
          month,
          status: statusFilter === "all" ? undefined : statusFilter,
          seasonality_tag: tagFilter === "all" ? undefined : tagFilter,
          supplier_id: supplierFilter ? Number(supplierFilter) : undefined,
          min_confidence: confidenceFilter === "all" ? undefined : confidenceFilter,
          sort_by: sortBy,
          limit: 500,
        }),
      ])
        .then(([loadedSummary, loadedProducts]) => {
          if (active) {
            setSummary(loadedSummary);
            setProducts({ data: loadedProducts, loading: false, error: null });
          }
        })
        .catch((loadError: Error) => {
          if (active) {
            setProducts({ data: [], loading: false, error: loadError.message });
            setSummaryError(loadError.message);
          }
        });
    },
    [confidenceFilter, month, sortBy, statusFilter, supplierFilter, tagFilter],
  );

  useEffect(() => {
    let active = true;
    loadSeasonality(active);
    return () => {
      active = false;
    };
  }, [loadSeasonality]);

  const visibleProducts = useMemo(() => {
    const filtered = products.data.filter((product) => {
      if (stockFilter === "out_of_stock" && stockStatus(product) !== "out_of_stock") return false;
      if (stockFilter === "low_stock" && stockStatus(product) !== "low_stock") return false;
      if (stockFilter === "in_stock" && stockStatus(product) !== "in_stock") return false;
      if (supplierAssignmentFilter === "assigned" && !product.supplier_id) return false;
      if (supplierAssignmentFilter === "missing" && product.supplier_id) return false;
      if (quickFilter === "in_season_out_of_stock") {
        return product.current_seasonality_status === "in_season" && stockStatus(product) === "out_of_stock";
      }
      if (quickFilter === "in_season_low_stock") {
        return product.current_seasonality_status === "in_season" && stockStatus(product) !== "in_stock";
      }
      if (quickFilter === "approaching_low_stock") {
        return product.current_seasonality_status === "approaching_season" && stockStatus(product) !== "in_stock";
      }
      if (quickFilter === "high_confidence_seasonal") {
        return product.confidence_label === "high" && !["year_round", "insufficient_data"].includes(product.seasonality_tag ?? "");
      }
      if (quickFilter === "seasonal_missing_supplier") {
        return !product.supplier_id && !["year_round", "insufficient_data"].includes(product.seasonality_tag ?? "");
      }
      if (quickFilter === "seasonal_missing_lead_time") {
        return !["year_round", "insufficient_data"].includes(product.seasonality_tag ?? "");
      }
      return true;
    });

    return [...filtered].sort((left, right) => {
      if (sortBy === "current_stock") {
        return Number(left.current_stock || 0) - Number(right.current_stock || 0);
      }
      if (sortBy === "confidence") {
        return (
          (confidencePriority[right.confidence_label ?? "insufficient"] ?? 0) -
          (confidencePriority[left.confidence_label ?? "insufficient"] ?? 0)
        );
      }
      if (sortBy === "product_name") {
        return left.name.localeCompare(right.name);
      }
      const statusDiff =
        (seasonalityStatusPriority[right.current_seasonality_status] ?? 0) -
        (seasonalityStatusPriority[left.current_seasonality_status] ?? 0);
      if (statusDiff !== 0) return statusDiff;
      const indexDiff = Number(right.selected_month_index || 0) - Number(left.selected_month_index || 0);
      if (indexDiff !== 0) return indexDiff;
      const confidenceDiff =
        (confidencePriority[right.confidence_label ?? "insufficient"] ?? 0) -
        (confidencePriority[left.confidence_label ?? "insufficient"] ?? 0);
      if (confidenceDiff !== 0) return confidenceDiff;
      const stockDiff = Number(left.current_stock || 0) - Number(right.current_stock || 0);
      if (stockDiff !== 0) return stockDiff;
      return left.name.localeCompare(right.name);
    });
  }, [products.data, quickFilter, sortBy, stockFilter, supplierAssignmentFilter]);

  async function openDetail(product: SeasonalProduct) {
    setSelectedProduct(product);
    setDetailLoading(true);
    setDetailError(null);
    setForecast(null);
    setForecastError(null);
    try {
      setDetail(await getProductSeasonality(product.product_id, month));
    } catch (loadError) {
      setDetail(null);
      setDetailError((loadError as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  async function openForecast(product: SeasonalProduct) {
    setSelectedProduct(product);
    setForecastLoading(true);
    setForecastError(null);
    try {
      setForecast(await fetchProductForecast(product.product_id));
    } catch (loadError) {
      setForecast(null);
      setForecastError((loadError as Error).message);
    } finally {
      setForecastLoading(false);
    }
  }

  const usableSeasonality = summary
    ? summary.product_count - (summary.current_season_counts.insufficient_data ?? 0)
    : 0;

  return (
    <div className="review-stack" aria-label="Seasonality dashboard">
      <section className="detail-panel">
        <div className="section-header">
          <div>
            <h2>Seasonality</h2>
            <p className="muted-text">
              Seasonality is advisory and does not automatically change recommended purchase quantity.
            </p>
          </div>
          <label>
            <span>Month</span>
            <select value={month} onChange={(event) => setMonth(Number(event.target.value))}>
              {monthNames.map((name, index) => (
                <option key={name} value={index + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {summaryError && <div className="state error">Could not load seasonality: {summaryError}</div>}
        {summary && (
          <div className="summary-grid" aria-label="Seasonality summary cards">
            <SummaryCard label="Total OrderPro products" value={summary.product_count} />
            <SummaryCard label="Products with usable seasonality" value={usableSeasonality} />
            <SummaryCard label="In season" value={summary.current_season_counts.in_season ?? 0} />
            <SummaryCard label="Approaching season" value={summary.current_season_counts.approaching_season ?? 0} />
            <SummaryCard label="Off season" value={summary.current_season_counts.off_season ?? 0} />
            <SummaryCard label="Year-round" value={summary.current_season_counts.year_round ?? 0} />
            <SummaryCard label="Insufficient data" value={summary.current_season_counts.insufficient_data ?? 0} />
            <SummaryCard label="High-confidence profiles" value={summary.confidence_counts.high ?? 0} />
            <SummaryCard label="Medium-confidence profiles" value={summary.confidence_counts.medium ?? 0} />
            <SummaryCard label="Low-confidence profiles" value={summary.confidence_counts.low ?? 0} />
          </div>
        )}
        {summary && (
          <div className="classification-row" aria-label="Recurring classification counts">
            {["winter", "spring", "summer", "autumn", "multi_peak", "year_round", "insufficient_data"].map((tag) => (
              <span className="selected-pill" key={tag}>
                {seasonalityTagLabel(tag)}: {summary.classification_counts[tag] ?? 0}
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="detail-panel" aria-label="Seasonality filters">
        <div className="filter-grid">
          <label>
            <span>Current status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="in_season">In season</option>
              <option value="approaching_season">Approaching season</option>
              <option value="off_season">Off season</option>
              <option value="year_round">Year-round</option>
              <option value="insufficient_data">Insufficient data</option>
            </select>
          </label>
          <label>
            <span>Recurring tag</span>
            <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="winter">Winter</option>
              <option value="spring">Spring</option>
              <option value="summer">Summer</option>
              <option value="autumn">Autumn</option>
              <option value="multi_peak">Multi-peak</option>
              <option value="year_round">Year-round</option>
              <option value="insufficient_data">Insufficient data</option>
            </select>
          </label>
          <label>
            <span>Supplier ID</span>
            <input value={supplierFilter} onChange={(event) => setSupplierFilter(event.target.value)} />
          </label>
          <label>
            <span>Confidence</span>
            <select value={confidenceFilter} onChange={(event) => setConfidenceFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="insufficient">Insufficient</option>
            </select>
          </label>
          <label>
            <span>Stock</span>
            <select value={stockFilter} onChange={(event) => setStockFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="out_of_stock">Out of stock</option>
              <option value="low_stock">Low stock</option>
              <option value="in_stock">In stock</option>
            </select>
          </label>
          <label>
            <span>Assigned supplier</span>
            <select
              value={supplierAssignmentFilter}
              onChange={(event) => setSupplierAssignmentFilter(event.target.value)}
            >
              <option value="all">All</option>
              <option value="assigned">Supplier assigned</option>
              <option value="missing">Missing supplier</option>
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              <option value="seasonal_index">Seasonal index</option>
              <option value="current_stock">Current stock</option>
              <option value="confidence">Confidence</option>
              <option value="product_name">Product name</option>
            </select>
          </label>
          <label>
            <span>Quick filter</span>
            <select value={quickFilter} onChange={(event) => setQuickFilter(event.target.value)}>
              <option value="none">None</option>
              <option value="in_season_out_of_stock">In season and out of stock</option>
              <option value="in_season_low_stock">In season and low stock</option>
              <option value="approaching_low_stock">Approaching season and low stock</option>
              <option value="high_confidence_seasonal">High-confidence seasonal products</option>
              <option value="seasonal_missing_supplier">Seasonal products missing supplier</option>
              <option value="seasonal_missing_lead_time">Seasonal products missing lead time</option>
            </select>
          </label>
        </div>
      </section>

      <SeasonalProductsTable
        loading={products.loading}
        error={products.error}
        onOpenDetail={openDetail}
        onOpenForecast={openForecast}
        products={visibleProducts}
      />

      {selectedProduct && (
        <section className="detail-panel" aria-label="Selected seasonal product">
          <h2>{selectedProduct.name}</h2>
          {detailLoading && <div className="state">Loading seasonality detail...</div>}
          {detailError && <div className="state error">Could not load seasonality detail: {detailError}</div>}
          {detail && <SeasonalityDetail detail={detail} product={selectedProduct} />}
          {forecastLoading && <div className="state">Loading forecast...</div>}
          {forecastError && <div className="state error">Could not load forecast: {forecastError}</div>}
          {forecast && <SeasonalityForecastSummary forecast={forecast} />}
        </section>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="summary-card">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SeasonalProductsTable({
  error,
  loading,
  onOpenDetail,
  onOpenForecast,
  products,
}: {
  error: string | null;
  loading: boolean;
  onOpenDetail: (product: SeasonalProduct) => void;
  onOpenForecast: (product: SeasonalProduct) => void;
  products: SeasonalProduct[];
}) {
  if (loading) return <div className="state">Loading seasonal products...</div>;
  if (error) return <div className="state error">Could not load seasonal products: {error}</div>;

  return (
    <section className="table-wrap" aria-label="Seasonal product table">
      <table>
        <thead>
          <tr>
            <th>Product ID</th>
            <th>OrderPro SKU</th>
            <th>Product name</th>
            <th>Supplier</th>
            <th>Current stock</th>
            <th>Recurring tag</th>
            <th>Current month status</th>
            <th>Month units</th>
            <th>Month index</th>
            <th>Peak months</th>
            <th>Primary season</th>
            <th>Strength</th>
            <th>Confidence</th>
            <th>History</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <tr key={product.product_id}>
              <td>{product.product_id}</td>
              <td>{formatValue(product.orderpro_sku)}</td>
              <td>{product.name}</td>
              <td>
                {formatValue(product.supplier_name)}
                {!product.supplier_id && <div className="review-need">Missing supplier</div>}
              </td>
              <td>
                {formatValue(product.current_stock)}
                {stockStatus(product) === "out_of_stock" && <div className="review-need">Out of stock</div>}
                {stockStatus(product) === "low_stock" && <div className="review-need">Low stock</div>}
              </td>
              <td>{seasonalityTagLabel(product.seasonality_tag)}</td>
              <td>
                <span className={seasonalityStatusClassName(product.current_seasonality_status)}>
                  {seasonalityStatusLabel(product.current_seasonality_status)}
                </span>
              </td>
              <td>{formatValue(product.selected_month_units)}</td>
              <td>{formatValue(product.selected_month_index)}</td>
              <td>{formatMonths(product.peak_months)}</td>
              <td>{formatValue(product.primary_season)}</td>
              <td>{formatValue(product.seasonality_strength)}</td>
              <td>
                {formatValue(product.confidence_score)}{" "}
                <span className={product.confidence_label === "low" ? "status needs-review" : "status mapped"}>
                  {formatValue(product.confidence_label)}
                </span>
                {product.confidence_label === "low" && <div className="review-need">Review manually</div>}
              </td>
              <td>
                {formatValue(product.history_start)} to {formatValue(product.history_end)}
                <div>{formatValue(product.years_covered)} years</div>
              </td>
              <td>
                <div className="action-row">
                  <button onClick={() => onOpenDetail(product)} type="button">
                    Details
                  </button>
                  <button onClick={() => onOpenForecast(product)} type="button">
                    View Forecast
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {products.length === 0 && <div className="state">No seasonal products match these filters.</div>}
    </section>
  );
}

function SeasonalityDetail({
  detail,
  product,
}: {
  detail: ProductSeasonalityDetail;
  product: SeasonalProduct;
}) {
  const months = Array.from({ length: 12 }, (_, index) => index + 1);
  return (
    <div className="review-stack">
      <dl className="detail-list">
        <div><dt>Product</dt><dd>{detail.name} ({formatValue(detail.orderpro_sku)})</dd></div>
        <div><dt>Supplier</dt><dd>{formatValue(product.supplier_name)}</dd></div>
        <div><dt>Current stock</dt><dd>{formatValue(product.current_stock)}</dd></div>
        <div><dt>Recurring classification</dt><dd>{seasonalityTagLabel(detail.seasonality_tag)}</dd></div>
        <div><dt>Current status</dt><dd>{seasonalityStatusLabel(detail.current_interpretation.current_status)}</dd></div>
        <div><dt>Primary season</dt><dd>{formatValue(detail.primary_season)}</dd></div>
        <div><dt>Peak months</dt><dd>{formatMonths(detail.peak_months)}</dd></div>
        <div><dt>Low months</dt><dd>{formatMonths(detail.low_months)}</dd></div>
        <div><dt>Confidence</dt><dd>{detail.confidence_score} ({detail.confidence_label})</dd></div>
        <div><dt>History</dt><dd>{formatValue(detail.history_start)} to {formatValue(detail.history_end)}, {detail.years_covered} years, {detail.active_months} active months</dd></div>
        <div><dt>Historical links</dt><dd>{detail.direct_history_row_count} direct rows, {detail.linked_history_row_count} linked rows from {detail.contributing_historical_product_ids.join(", ") || "none"}</dd></div>
        <div><dt>Reconciliation methods</dt><dd>{detail.reconciliation_methods.join(", ") || "-"}</dd></div>
        <div><dt>Advisory explanation</dt><dd>{detail.current_interpretation.advisory_message}</dd></div>
      </dl>
      <section className="table-wrap nested-table" aria-label="Monthly seasonality values">
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th>Monthly units</th>
              <th>Monthly index</th>
            </tr>
          </thead>
          <tbody>
            {months.map((month) => (
              <tr key={month}>
                <td>{formatMonth(month)}</td>
                <td>{formatValue(detail.monthly_units?.[String(month)])}</td>
                <td>{formatValue(detail.monthly_indices?.[String(month)])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function SeasonalityForecastSummary({ forecast }: { forecast: ForecastResponse }) {
  return (
    <section className="nested-panel" aria-label="Seasonality forecast summary">
      <h3>Forecast</h3>
      <div className="state warning">
        Seasonality is currently advisory and does not automatically change the recommended purchase quantity.
      </div>
      <dl className="detail-list">
        <div><dt>Current stock</dt><dd>{formatValue(forecast.current_stock)}</dd></div>
        <div><dt>Open demand</dt><dd>{formatValue(forecast.total_open_demand)}</dd></div>
        <div><dt>Average daily usage</dt><dd>{formatValue(forecast.avg_daily_usage)}</dd></div>
        <div><dt>Lead time</dt><dd>{formatValue(forecast.lead_time_days_used)}</dd></div>
        <div><dt>Recommended action</dt><dd>{formatValue(forecast.recommended_action)}</dd></div>
        <div><dt>Recommended quantity</dt><dd>{formatValue(forecast.recommended_qty)}</dd></div>
        <div><dt>Seasonality advisory</dt><dd>{formatValue(forecast.seasonality_context?.advisory_message)}</dd></div>
      </dl>
    </section>
  );
}

function PurchaseOrdersPanel({ initialPoId }: { initialPoId: number | null }) {
  const [purchaseOrders, setPurchaseOrders] = useState<ResourceState<PurchaseOrder>>(initialResource);
  const [selectedPo, setSelectedPo] = useState<PurchaseOrder | null>(null);
  const [selectedPoError, setSelectedPoError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [lineActionLoading, setLineActionLoading] = useState(false);
  const [headerActionLoading, setHeaderActionLoading] = useState(false);

  const loadPurchaseOrders = useCallback((active = true) => {
    listPurchaseOrders()
      .then((loadedPurchaseOrders) => {
        if (active) {
          setPurchaseOrders({ data: loadedPurchaseOrders, loading: false, error: null });
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setPurchaseOrders({ data: [], loading: false, error: loadError.message });
        }
      });
  }, []);

  useEffect(() => {
    let active = true;
    loadPurchaseOrders(active);
    return () => {
      active = false;
    };
  }, [loadPurchaseOrders]);

  async function refreshSelected(poId: number) {
    const loadedPo = await getPurchaseOrder(poId);
    setSelectedPo(loadedPo);
    loadPurchaseOrders();
  }

  async function handleSelect(poId: number) {
    setSelectedPoError(null);
    setActionError(null);
    try {
      await refreshSelected(poId);
    } catch (loadError) {
      setSelectedPo(null);
      setSelectedPoError((loadError as Error).message);
    }
  }

  useEffect(() => {
    if (initialPoId) {
      handleSelect(initialPoId);
    }
  }, [initialPoId]);

  async function handleCreate(payload: CreatePurchaseOrderRequest) {
    setCreating(true);
    setActionError(null);
    try {
      const created = await createPurchaseOrder(payload);
      setSelectedPo(created);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function handleAddLine(payload: AddPurchaseOrderLineRequest) {
    if (!selectedPo) {
      return;
    }
    setLineActionLoading(true);
    setActionError(null);
    try {
      const updated = await addPurchaseOrderLine(selectedPo.id, payload);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLineActionLoading(false);
    }
  }

  async function handleUpdateLine(lineId: number, payload: UpdatePurchaseOrderLineRequest) {
    if (!selectedPo) {
      return;
    }
    setLineActionLoading(true);
    setActionError(null);
    try {
      const updated = await updatePurchaseOrderLine(selectedPo.id, lineId, payload);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setLineActionLoading(false);
    }
  }

  async function handleSubmitForApproval() {
    if (!selectedPo) {
      return;
    }
    setHeaderActionLoading(true);
    setActionError(null);
    try {
      const updated = await submitPurchaseOrderForApproval(selectedPo.id);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setHeaderActionLoading(false);
    }
  }

  async function handleApprove(approvedBy: string | null) {
    if (!selectedPo) {
      return;
    }
    setHeaderActionLoading(true);
    setActionError(null);
    try {
      const updated = await approvePurchaseOrder(selectedPo.id, { approved_by: approvedBy });
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setHeaderActionLoading(false);
    }
  }

  async function handleIssue() {
    if (!selectedPo || !window.confirm("Mark this purchase order as internally issued? This will not send it externally.")) {
      return;
    }
    setHeaderActionLoading(true);
    setActionError(null);
    try {
      const updated = await issuePurchaseOrder(selectedPo.id);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setHeaderActionLoading(false);
    }
  }

  async function handleReceive() {
    if (!selectedPo || !window.confirm("Mark this purchase order as received? This will not update stock yet.")) {
      return;
    }
    setHeaderActionLoading(true);
    setActionError(null);
    try {
      const updated = await receivePurchaseOrder(selectedPo.id);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setHeaderActionLoading(false);
    }
  }

  async function handleCancel() {
    if (!selectedPo || !window.confirm("Cancel this purchase order?")) {
      return;
    }
    setHeaderActionLoading(true);
    setActionError(null);
    try {
      const updated = await cancelPurchaseOrder(selectedPo.id);
      setSelectedPo(updated);
      loadPurchaseOrders();
    } catch (loadError) {
      setActionError((loadError as Error).message);
    } finally {
      setHeaderActionLoading(false);
    }
  }

  return (
    <div className="review-stack">
      <CreatePurchaseOrderForm creating={creating} onCreate={handleCreate} />
      <PurchaseOrdersTable
        onSelect={handleSelect}
        purchaseOrders={purchaseOrders.data}
        resource={purchaseOrders}
        selectedPoId={selectedPo?.id ?? null}
      />
      {selectedPoError && <div className="state error">Could not load PO: {selectedPoError}</div>}
      {actionError && <div className="state error">Purchase order action failed: {actionError}</div>}
      {selectedPo ? (
        <PurchaseOrderDetail
          headerActionLoading={headerActionLoading}
          lineActionLoading={lineActionLoading}
          onAddLine={handleAddLine}
          onApprove={handleApprove}
          onCancel={handleCancel}
          onIssue={handleIssue}
          onReceive={handleReceive}
          onSubmitForApproval={handleSubmitForApproval}
          onUpdateLine={handleUpdateLine}
          purchaseOrder={selectedPo}
        />
      ) : (
        <div className="state">Select a purchase order to view details.</div>
      )}
    </div>
  );
}

function CreatePurchaseOrderForm({
  creating,
  onCreate,
}: {
  creating: boolean;
  onCreate: (payload: CreatePurchaseOrderRequest) => Promise<void>;
}) {
  const [supplierId, setSupplierId] = useState("");
  const [notes, setNotes] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedSupplierId = Number(supplierId);
    if (!Number.isInteger(parsedSupplierId) || parsedSupplierId <= 0) {
      setValidationError("Supplier ID is required.");
      return;
    }
    setValidationError(null);
    await onCreate({
      supplier_id: parsedSupplierId,
      notes: notes || null,
      created_by: createdBy || null,
    });
  }

  return (
    <section className="detail-panel" aria-label="Create draft purchase order">
      <h2>Create Draft PO</h2>
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Supplier ID</span>
          <input onChange={(event) => setSupplierId(event.target.value)} value={supplierId} />
        </label>
        <label>
          <span>Notes</span>
          <input onChange={(event) => setNotes(event.target.value)} value={notes} />
        </label>
        <label>
          <span>Created by</span>
          <input onChange={(event) => setCreatedBy(event.target.value)} value={createdBy} />
        </label>
        <button disabled={creating} type="submit">
          {creating ? "Creating..." : "Create Draft PO"}
        </button>
      </form>
      {validationError && <div className="state error">{validationError}</div>}
    </section>
  );
}

function PurchaseOrdersTable({
  onSelect,
  purchaseOrders,
  resource,
  selectedPoId,
}: {
  onSelect: (poId: number) => void;
  purchaseOrders: PurchaseOrder[];
  resource: ResourceState<PurchaseOrder>;
  selectedPoId: number | null;
}) {
  if (resource.loading) {
    return <div className="state">Loading purchase orders...</div>;
  }
  if (resource.error) {
    return <div className="state error">Could not load purchase orders: {resource.error}</div>;
  }

  return (
    <section className="table-wrap" aria-label="Purchase orders list">
      <table>
        <thead>
          <tr>
            <th>PO ID</th>
            <th>Supplier</th>
            <th>Status</th>
            <th>Total</th>
            <th>Currency</th>
            <th>Created</th>
            <th>Notes</th>
            <th>Lines</th>
            <th>View</th>
          </tr>
        </thead>
        <tbody>
          {purchaseOrders.map((po) => (
            <tr key={po.id}>
              <td>{po.id}</td>
              <td>{formatValue(po.supplier_name)}</td>
              <td>
                <span className={purchaseOrderStatusClassName(po.status)}>{po.status}</span>
              </td>
              <td>{formatValue(po.total_amount)}</td>
              <td>{formatValue(po.currency)}</td>
              <td>{formatDate(po.created_at)}</td>
              <td>{formatValue(po.notes)}</td>
              <td>{po.lines.length}</td>
              <td>
                <button onClick={() => onSelect(po.id)} type="button">
                  {selectedPoId === po.id ? "Viewing" : "View"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {purchaseOrders.length === 0 && <div className="state">No purchase orders found.</div>}
    </section>
  );
}

function PurchaseOrderDetail({
  headerActionLoading,
  lineActionLoading,
  onAddLine,
  onApprove,
  onCancel,
  onIssue,
  onReceive,
  onSubmitForApproval,
  onUpdateLine,
  purchaseOrder,
}: {
  headerActionLoading: boolean;
  lineActionLoading: boolean;
  onAddLine: (payload: AddPurchaseOrderLineRequest) => Promise<void>;
  onApprove: (approvedBy: string | null) => Promise<void>;
  onCancel: () => void;
  onIssue: () => void;
  onReceive: () => void;
  onSubmitForApproval: () => void;
  onUpdateLine: (lineId: number, payload: UpdatePurchaseOrderLineRequest) => Promise<void>;
  purchaseOrder: PurchaseOrder;
}) {
  const [approvedBy, setApprovedBy] = useState("");
  const canEdit = purchaseOrder.status === "draft";
  const canCancel = purchaseOrder.status === "draft" || purchaseOrder.status === "pending_approval";
  const canApprove = purchaseOrder.status === "pending_approval";
  const canIssue = purchaseOrder.status === "approved";
  const canReceive = purchaseOrder.status === "issued";

  return (
    <section className="detail-panel" aria-label="Purchase order details">
      <div className="section-header">
        <h2>Purchase Order {purchaseOrder.id}</h2>
        <div className="action-row">
          {canEdit && (
            <button disabled={headerActionLoading} onClick={onSubmitForApproval} type="button">
              Submit for Approval
            </button>
          )}
          {canApprove && (
            <form
              className="approval-form"
              onSubmit={(event) => {
                event.preventDefault();
                onApprove(approvedBy || null);
              }}
            >
              <label>
                <span>Approved by</span>
                <input
                  onChange={(event) => setApprovedBy(event.target.value)}
                  value={approvedBy}
                />
              </label>
              <button disabled={headerActionLoading} type="submit">
                Approve
              </button>
            </form>
          )}
          {canIssue && (
            <button disabled={headerActionLoading} onClick={onIssue} type="button">
              Issue
            </button>
          )}
          {canReceive && (
            <button disabled={headerActionLoading} onClick={onReceive} type="button">
              Receive
            </button>
          )}
          {canCancel && (
            <button disabled={headerActionLoading} onClick={onCancel} type="button">
              Cancel
            </button>
          )}
        </div>
      </div>
      {canEdit && (
        <div className="state">
          Submit for approval only moves this draft into review; it does not issue the PO.
        </div>
      )}
      {canIssue && (
        <div className="state warning">
          Issue only marks this PO as internally issued. It does not send it externally.
        </div>
      )}
      <dl className="detail-list">
        <div>
          <dt>Supplier</dt>
          <dd>{formatValue(purchaseOrder.supplier_name)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <span className={purchaseOrderStatusClassName(purchaseOrder.status)}>
              {purchaseOrder.status}
            </span>
          </dd>
        </div>
        <div>
          <dt>Notes</dt>
          <dd>{formatValue(purchaseOrder.notes)}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>
            {formatValue(purchaseOrder.total_amount)} {formatValue(purchaseOrder.currency)}
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDate(purchaseOrder.created_at)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatDate(purchaseOrder.updated_at)}</dd>
        </div>
        <div>
          <dt>Approved</dt>
          <dd>{formatDate(purchaseOrder.approved_at)}</dd>
        </div>
        <div>
          <dt>Issued</dt>
          <dd>{formatDate(purchaseOrder.issued_at)}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{formatDate(purchaseOrder.received_at)}</dd>
        </div>
        <div>
          <dt>Cancelled</dt>
          <dd>{formatDate(purchaseOrder.cancelled_at)}</dd>
        </div>
      </dl>

      {canEdit && <AddPurchaseOrderLineForm loading={lineActionLoading} onAddLine={onAddLine} />}
      <PurchaseOrderLinesTable
        canEdit={canEdit}
        lineActionLoading={lineActionLoading}
        onUpdateLine={onUpdateLine}
        purchaseOrder={purchaseOrder}
      />
    </section>
  );
}

function AddPurchaseOrderLineForm({
  loading,
  onAddLine,
}: {
  loading: boolean;
  onAddLine: (payload: AddPurchaseOrderLineRequest) => Promise<void>;
}) {
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedProductId = Number(productId);
    const parsedQuantity = Number(quantity);

    if (!Number.isInteger(parsedProductId) || parsedProductId <= 0) {
      setValidationError("Product ID is required.");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      setValidationError("Quantity must be greater than zero.");
      return;
    }

    setValidationError(null);
    await onAddLine({
      product_id: parsedProductId,
      quantity: parsedQuantity,
      notes: notes || null,
    });
  }

  return (
    <section className="nested-panel" aria-label="Add purchase order line">
      <h3>Add Line</h3>
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Product ID</span>
          <input
            onChange={(event) => setProductId(event.target.value)}
            value={productId}
          />
        </label>
        <label>
          <span>Quantity</span>
          <input onChange={(event) => setQuantity(event.target.value)} value={quantity} />
        </label>
        <label>
          <span>Notes</span>
          <input onChange={(event) => setNotes(event.target.value)} value={notes} />
        </label>
        <button disabled={loading} type="submit">
          {loading ? "Adding..." : "Add Line"}
        </button>
      </form>
      {validationError && <div className="state error">{validationError}</div>}
    </section>
  );
}

function PurchaseOrderLinesTable({
  canEdit,
  lineActionLoading,
  onUpdateLine,
  purchaseOrder,
}: {
  canEdit: boolean;
  lineActionLoading: boolean;
  onUpdateLine: (lineId: number, payload: UpdatePurchaseOrderLineRequest) => Promise<void>;
  purchaseOrder: PurchaseOrder;
}) {
  return (
    <section className="table-wrap nested-table" aria-label="Purchase order lines">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Legacy ProductSupplier ID</th>
            <th>Supplier SKU</th>
            <th>Supplier product</th>
            <th>Quantity</th>
            <th>Unit cost</th>
            <th>Currency</th>
            <th>Line total</th>
            <th>MOQ</th>
            <th>Pack size</th>
            <th>Lead time</th>
            <th>Notes</th>
            {canEdit && <th>Edit</th>}
          </tr>
        </thead>
        <tbody>
          {purchaseOrder.lines.map((line) => (
            <tr key={line.id}>
              <td>{formatValue(line.product_name ?? line.product_id)}</td>
              <td>{formatValue(line.product_supplier_id)}</td>
              <td>{formatValue(line.supplier_sku)}</td>
              <td>{formatValue(line.supplier_product_name)}</td>
              <td>{formatValue(line.quantity)}</td>
              <td>{formatValue(line.unit_cost)}</td>
              <td>{formatValue(line.currency)}</td>
              <td>{formatValue(line.line_total)}</td>
              <td>{formatValue(line.minimum_order_quantity)}</td>
              <td>{formatValue(line.pack_size)}</td>
              <td>{formatValue(line.lead_time_days)}</td>
              <td>{formatValue(line.notes)}</td>
              {canEdit && (
                <td>
                  <InlineLineEditor
                    disabled={lineActionLoading}
                    line={line}
                    onUpdateLine={onUpdateLine}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {purchaseOrder.lines.length === 0 && <div className="state">No lines added yet.</div>}
    </section>
  );
}

function InlineLineEditor({
  disabled,
  line,
  onUpdateLine,
}: {
  disabled: boolean;
  line: PurchaseOrder["lines"][number];
  onUpdateLine: (lineId: number, payload: UpdatePurchaseOrderLineRequest) => Promise<void>;
}) {
  const [quantity, setQuantity] = useState(String(line.quantity));
  const [notes, setNotes] = useState(line.notes ?? "");

  return (
    <form
      className="inline-form"
      onSubmit={(event) => {
        event.preventDefault();
        onUpdateLine(line.id, {
          quantity: Number(quantity),
          notes: notes || null,
        });
      }}
    >
      <input
        aria-label={`Quantity for line ${line.id}`}
        onChange={(event) => setQuantity(event.target.value)}
        value={quantity}
      />
      <input
        aria-label={`Notes for line ${line.id}`}
        onChange={(event) => setNotes(event.target.value)}
        value={notes}
      />
      <button disabled={disabled} type="submit">
        Save
      </button>
    </form>
  );
}

export default App;
