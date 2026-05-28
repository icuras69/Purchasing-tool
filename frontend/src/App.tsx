import { Fragment, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  confirmProductSupplier,
  createProductSupplier,
  fetchProductForecast,
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
  rejectProductSupplier,
  setPreferredProductSupplier,
  unsetPreferredProductSupplier,
} from "./api";
import { productMatchesQuery, supplierDisplayName } from "./productDisplay";
import type {
  ForecastResponse,
  ForecastSupplierContext,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  WeakMapping,
} from "./types";

type TabId = "products" | "unmapped" | "weak" | "mappings" | "forecast";

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
        <ProductTable
          expandedProductId={expandedProductId}
          onExpandedProductIdChange={setExpandedProductId}
          products={filteredProducts}
          resource={products}
        />
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
    </main>
  );
}

interface ProductTableProps {
  expandedProductId: number | null;
  onExpandedProductIdChange: (productId: number | null) => void;
  products: Product[];
  resource: ResourceState<Product>;
}

function ProductTable({
  expandedProductId,
  onExpandedProductIdChange,
  products,
  resource,
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
                    <td colSpan={8}>
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

export default App;
