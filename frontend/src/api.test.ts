import { afterEach, describe, expect, it, vi } from "vitest";
import {
  apiUrl,
  assignManualSupplierCleanupCandidate,
  clearStoredAccessToken,
  exportDemandHistoryCsv,
  exportForecastReconciliationCsv,
  exportPurchaseOrderCsv,
  fetchProducts,
  getDemandHistoryProduct,
  getDemandHistoryProducts,
  getForecastReconciliationProduct,
  getForecastReconciliationProducts,
  getManualSupplierCleanupCandidates,
  getStoredAccessToken,
  isAuthEnabled,
  loginAdmin,
  reviewManualSupplierCleanupCandidate,
  searchManualSupplierCleanupSuppliers,
  setUnauthorizedHandler,
  storeAccessToken,
} from "./api";

describe("apiUrl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    clearStoredAccessToken();
    setUnauthorizedHandler(null);
  });

  it("uses the local backend fallback when no base URL is supplied", () => {
    expect(apiUrl("/health", "http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000/health",
    );
  });

  it("normalizes a trailing slash on the configured backend URL", () => {
    expect(apiUrl("/products/", "https://purchasing-ai-api.onrender.com/")).toBe(
      "https://purchasing-ai-api.onrender.com/products/",
    );
  });

  it("stores the bearer token in sessionStorage after login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ access_token: "abc123", token_type: "bearer", expires_in: 3600 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await loginAdmin({ email: "admin@example.com", password: "secret-password" });

    expect(getStoredAccessToken()).toBe("abc123");
  });

  it("adds bearer token to authenticated API requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("stored-token");

    await fetchProducts();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/products/"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer stored-token" }),
      }),
    );
  });

  it("defaults authentication to enabled unless explicitly disabled", () => {
    expect(isAuthEnabled()).toBe(true);

    vi.stubEnv("VITE_AUTH_ENABLED", "false");

    expect(isAuthEnabled()).toBe(false);
  });

  it("does not add authorization headers when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("stored-token");

    await fetchProducts();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/products/"),
      expect.objectContaining({
        headers: {},
      }),
    );
  });

  it("clears token and notifies app on protected 401 responses", async () => {
    const onUnauthorized = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid or expired authentication credentials." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    storeAccessToken("expired-token");
    setUnauthorizedHandler(onUnauthorized);

    await expect(fetchProducts()).rejects.toThrow("Invalid or expired authentication credentials.");

    expect(getStoredAccessToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not redirect to login on 401 responses when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const onUnauthorized = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Still unavailable." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    storeAccessToken("ignored-token");
    setUnauthorizedHandler(onUnauthorized);

    await expect(fetchProducts()).rejects.toThrow("Still unavailable.");

    expect(getStoredAccessToken()).toBe("ignored-token");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("exports purchase order CSV with bearer token and response filename", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("csv", {
        status: 200,
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="purchase_order_500.csv"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("stored-token");

    const result = await exportPurchaseOrderCsv(500);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/purchase-orders/500/export.csv"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer stored-token" }),
      }),
    );
    expect(result.filename).toBe("purchase_order_500.csv");
    expect(await result.blob.text()).toBe("csv");
  });

  it("exports purchase order CSV without auth header when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("csv", {
        status: 200,
        headers: { "Content-Type": "text/csv" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("ignored-token");

    const result = await exportPurchaseOrderCsv(500);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/purchase-orders/500/export.csv"),
      expect.objectContaining({ headers: {} }),
    );
    expect(result.filename).toBeNull();
  });

  it("fetches forecast reconciliation products with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: 1, page_size: 25, total: 0, total_pages: 0, summary: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getForecastReconciliationProducts({
      page: 2,
      search: "halter",
      status: "blocked",
      missing_input: "supplier_id",
      has_open_demand: true,
    });

    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/api/forecast-reconciliation/products?");
    expect(calledUrl).toContain("page=2");
    expect(calledUrl).toContain("search=halter");
    expect(calledUrl).toContain("status=blocked");
    expect(calledUrl).toContain("missing_input=supplier_id");
    expect(calledUrl).toContain("has_open_demand=true");
  });

  it("fetches one forecast reconciliation detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ product_id: 77 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getForecastReconciliationProduct(77);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/forecast-reconciliation/products/77"),
      expect.any(Object),
    );
  });

  it("exports forecast readiness CSV without auth header when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("csv", {
        status: 200,
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="forecast_readiness.csv"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("ignored-token");

    const result = await exportForecastReconciliationCsv({ status: "ready" });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/forecast-reconciliation/export.csv?status=ready"),
      expect.objectContaining({ headers: {} }),
    );
    expect(result.filename).toBe("forecast_readiness.csv");
  });

  it("fetches demand history products with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: 1, page_size: 25, total: 0, total_pages: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getDemandHistoryProducts({
      page: 2,
      search: "halter",
      has_history: false,
      has_recent_demand: true,
      supplier_id: 34,
      sort_by: "latest_demand_date",
    });

    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/api/demand-history-reconciliation/products?");
    expect(calledUrl).toContain("page=2");
    expect(calledUrl).toContain("search=halter");
    expect(calledUrl).toContain("has_history=false");
    expect(calledUrl).toContain("has_recent_demand=true");
    expect(calledUrl).toContain("supplier_id=34");
    expect(calledUrl).toContain("sort_by=latest_demand_date");
  });

  it("fetches one demand history detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ product_id: 7832 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getDemandHistoryProduct(7832);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/demand-history-reconciliation/products/7832"),
      expect.any(Object),
    );
  });

  it("exports demand history CSV without auth header when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("csv", {
        status: 200,
        headers: {
          "Content-Type": "text/csv",
          "Content-Disposition": 'attachment; filename="demand_coverage.csv"',
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("ignored-token");

    const result = await exportDemandHistoryCsv({ has_history: true });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/demand-history-reconciliation/export.csv?has_history=true"),
      expect.objectContaining({ headers: {} }),
    );
    expect(result.filename).toBe("demand_coverage.csv");
  });

  it("fetches manual supplier cleanup candidates with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], page: 1, page_size: 25, total: 0, total_pages: 0, summary: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getManualSupplierCleanupCandidates({
      search: "halter",
      priority_only: true,
      has_open_demand: true,
      page: 2,
    });

    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("/api/manual-supplier-cleanup/candidates?");
    expect(calledUrl).toContain("page=2");
    expect(calledUrl).toContain("search=halter");
    expect(calledUrl).toContain("priority_only=true");
    expect(calledUrl).toContain("has_open_demand=true");
  });

  it("searches cleanup suppliers and posts assignment payloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [], page: 1, page_size: 25, total: 0, total_pages: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    storeAccessToken("stored-token");

    await searchManualSupplierCleanupSuppliers({ search: "acme" });
    await assignManualSupplierCleanupCandidate(71, {
      supplier_id: 10,
      reviewed_by: "Maged",
      notes: "Confirmed",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/manual-supplier-cleanup/suppliers?search=acme"),
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/manual-supplier-cleanup/candidates/71/assign"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ supplier_id: 10, reviewed_by: "Maged", notes: "Confirmed" }),
        headers: expect.objectContaining({ Authorization: "Bearer stored-token" }),
      }),
    );
  });

  it("posts cleanup review without auth header when authentication is disabled", async () => {
    vi.stubEnv("VITE_AUTH_ENABLED", "false");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await reviewManualSupplierCleanupCandidate(71, { status: "deferred" });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/manual-supplier-cleanup/candidates/71/review"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
});
