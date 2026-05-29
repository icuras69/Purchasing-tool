import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  confirmProductSupplier,
  addPurchaseOrderLine,
  approvePurchaseOrder,
  cancelPurchaseOrder,
  acceptRecommendation,
  convertRecommendationToDraftPO,
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
  getPurchaseOrder,
  getRecommendation,
  issuePurchaseOrder,
  listRecommendations,
  listPurchaseOrders,
  receivePurchaseOrder,
  rejectRecommendation,
  rejectProductSupplier,
  setPreferredProductSupplier,
  submitPurchaseOrderForApproval,
  unsetPreferredProductSupplier,
  updatePurchaseOrderLine,
} from "./api";
import { productMatchesQuery, supplierDisplayName } from "./productDisplay";
import type {
  ForecastResponse,
  ForecastSupplierContext,
  RecommendationLLMExplanation,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  PurchaseOrder,
  PurchaseRecommendation,
  AddPurchaseOrderLineRequest,
  CreatePurchaseOrderRequest,
  DraftFromProductsResponse,
  UpdatePurchaseOrderLineRequest,
  WeakMapping,
} from "./types";

type TabId =
  | "products"
  | "unmapped"
  | "weak"
  | "mappings"
  | "forecast"
  | "purchase-orders"
  | "recommendations";

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
  { id: "purchase-orders", label: "Purchase Orders" },
  { id: "recommendations", label: "Recommendations" },
];

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
    return "ProductSupplier clean mapping";
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
            <th>Product name</th>
            <th>Current stock</th>
            <th>Preferred supplier</th>
            <th>Supplier count</th>
            <th>Mapping status</th>
            <th>Preferred supplier SKU</th>
            <th>Mappings</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => {
            const isExpanded = expandedProductId === product.id;
            const statusClass =
              product.mapping_status === "mapped" ? "status mapped" : "status unmapped";

            return (
              <Fragment key={product.id}>
                <tr>
                  <td>
                    <input
                      aria-label={`Select ${product.name} for draft PO`}
                      checked={selectedProductIds.includes(product.id)}
                      disabled={product.mapping_status === "unmapped"}
                      onChange={() => onToggleDraftSelection(product.id)}
                      type="checkbox"
                    />
                  </td>
                  <td>{product.id}</td>
                  <td>{product.name}</td>
                  <td>{formatValue(product.current_stock)}</td>
                  <td>{supplierDisplayName(product)}</td>
                  <td>{product.supplier_count}</td>
                  <td>
                    <span className={statusClass}>{product.mapping_status}</span>
                  </td>
                  <td>{formatValue(product.preferred_supplier_sku)}</td>
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
                    <td colSpan={9}>
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
  const [supplierId, setSupplierId] = useState("");
  const [createdBy, setCreatedBy] = useState("manual");
  const [notes, setNotes] = useState("Draft generated from product selection");
  const [creating, setCreating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [result, setResult] = useState<DraftFromProductsResponse | null>(null);

  const selectedProducts = products.filter((product) => selectedProductIds.includes(product.id));
  const selectedSupplierIds = Array.from(
    new Set(
      selectedProducts
        .map((product) => product.preferred_supplier_id)
        .filter((value): value is number => value !== null && value !== undefined),
    ),
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedSupplierId = Number(supplierId);
    if (selectedProductIds.length === 0) {
      setValidationError("Select at least one mapped product.");
      return;
    }
    if (!Number.isInteger(parsedSupplierId) || parsedSupplierId <= 0) {
      setValidationError("Supplier ID is required.");
      return;
    }

    setCreating(true);
    setValidationError(null);
    setCreateError(null);
    setResult(null);
    try {
      const created = await createDraftPurchaseOrderFromProducts({
        supplier_id: parsedSupplierId,
        product_ids: selectedProductIds,
        created_by: createdBy || "manual",
        notes: notes || "Draft generated from product selection",
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
          Preferred supplier IDs in selection: {selectedSupplierIds.join(", ")}
        </div>
      )}
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>Supplier ID</span>
          <input onChange={(event) => setSupplierId(event.target.value)} value={supplierId} />
        </label>
        <label>
          <span>Created by</span>
          <input onChange={(event) => setCreatedBy(event.target.value)} value={createdBy} />
        </label>
        <label>
          <span>Notes</span>
          <input onChange={(event) => setNotes(event.target.value)} value={notes} />
        </label>
        <button disabled={creating || selectedProductIds.length === 0} type="submit">
          {creating ? "Generating..." : "Generate Draft PO"}
        </button>
      </form>
      {selectedProductIds.length === 0 && (
        <div className="action-state">Select mapped products from the table below.</div>
      )}
      {validationError && <div className="state error">{validationError}</div>}
      {createError && <div className="state error">Draft generation failed: {createError}</div>}
      {result && (
        <div className="result-panel" aria-label="Draft PO generation result">
          <h3>Draft PO {result.purchase_order.id} created</h3>
          <dl className="detail-list">
            <div>
              <dt>Status</dt>
              <dd>
                <span className={purchaseOrderStatusClassName(result.purchase_order.status)}>
                  {result.purchase_order.status}
                </span>
              </dd>
            </div>
            <div>
              <dt>Created lines</dt>
              <dd>{result.summary.created_line_count}</dd>
            </div>
          </dl>
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
          <button onClick={() => onViewPurchaseOrder(result.purchase_order.id)} type="button">
            View Draft PO
          </button>
        </div>
      )}
    </section>
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
            <dt>Recommended action</dt>
            <dd>{formatValue(forecast.recommended_action)}</dd>
          </div>
          <div>
            <dt>Recommended quantity</dt>
            <dd>{formatValue(forecast.recommended_qty)}</dd>
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
    </div>
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
            <dt>Explanation</dt>
            <dd>{snapshotValue(forecastSnapshot, "explanation")}</dd>
          </div>
        </dl>
      </section>
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
  const [productSupplierId, setProductSupplierId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedProductSupplierId = Number(productSupplierId);
    const parsedQuantity = Number(quantity);

    if (!Number.isInteger(parsedProductSupplierId) || parsedProductSupplierId <= 0) {
      setValidationError("ProductSupplier ID is required.");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      setValidationError("Quantity must be greater than zero.");
      return;
    }

    setValidationError(null);
    await onAddLine({
      product_supplier_id: parsedProductSupplierId,
      quantity: parsedQuantity,
      notes: notes || null,
    });
  }

  return (
    <section className="nested-panel" aria-label="Add purchase order line">
      <h3>Add Line</h3>
      <form className="mapping-form" onSubmit={handleSubmit}>
        <label>
          <span>ProductSupplier ID</span>
          <input
            onChange={(event) => setProductSupplierId(event.target.value)}
            value={productSupplierId}
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
            <th>ProductSupplier ID</th>
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
              <td>{line.product_supplier_id}</td>
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
