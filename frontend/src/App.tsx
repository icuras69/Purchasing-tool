import { useEffect, useMemo, useState } from "react";
import { fetchProducts } from "./api";
import { productMatchesQuery, supplierDisplayName } from "./productDisplay";
import type { Product } from "./types";

function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [expandedProductId, setExpandedProductId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetchProducts()
      .then((loadedProducts) => {
        if (active) {
          setProducts(loadedProducts);
          setError(null);
        }
      })
      .catch((loadError: Error) => {
        if (active) {
          setError(loadError.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const filteredProducts = useMemo(
    () => products.filter((product) => productMatchesQuery(product, query)),
    [products, query],
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
            placeholder="Product or supplier"
          />
        </label>
      </header>

      {loading && <div className="state">Loading products...</div>}
      {error && <div className="state error">Could not load products: {error}</div>}

      {!loading && !error && (
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
              {filteredProducts.map((product) => {
                const isExpanded = expandedProductId === product.id;
                const statusClass =
                  product.mapping_status === "mapped" ? "status mapped" : "status unmapped";

                return (
                  <>
                    <tr key={product.id}>
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
                          type="button"
                          onClick={() => setExpandedProductId(isExpanded ? null : product.id)}
                          disabled={product.supplier_mappings.length === 0}
                        >
                          {isExpanded ? "Hide" : "View"}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${product.id}-details`}>
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
                                    <td>
                                      {formatValue(mapping.purchase_price)}
                                      {mapping.currency ? ` ${mapping.currency}` : ""}
                                    </td>
                                    <td>{formatValue(mapping.match_status)}</td>
                                    <td>{formatValue(mapping.match_method)}</td>
                                    <td>{mapping.is_preferred ? "Yes" : "No"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
          {filteredProducts.length === 0 && <div className="state">No products found.</div>}
        </section>
      )}
    </main>
  );
}

export default App;
