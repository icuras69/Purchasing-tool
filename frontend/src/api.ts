import type {
  ForecastResponse,
  ForecastReconciliationProduct,
  ForecastReconciliationProductsResponse,
  ForecastReconciliationSummary,
  ForecastInputAudit,
  ForecastReadinessSummary,
  AddPurchaseOrderLineRequest,
  ApprovePurchaseOrderRequest,
  AuthTokenResponse,
  CurrentAdmin,
  CreatePurchaseOrderRequest,
  DemandHistoryProduct,
  DemandHistoryProductsResponse,
  DemandHistorySummary,
  DraftFromProductsRequest,
  DraftFromProductsResponse,
  LoginRequest,
  ManualSupplierCleanupAssignRequest,
  ManualSupplierCleanupCandidate,
  ManualSupplierCleanupCandidatesResponse,
  ManualSupplierCleanupReviewRequest,
  ManualSupplierCleanupSummary,
  ManualSupplierCleanupSuppliersResponse,
  ManagerApprovedStaleQueueResponse,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  PurchaseOrder,
  PurchaseOrderExternalSendReadiness,
  PurchaseOrderPreflight,
  PurchaseRecommendation,
  RecommendationPOReadiness,
  RecommendationLLMExplanation,
  StaleDemandDecisionRequest,
  StaleDemandReviewDecision,
  StaleDemandReviewResponse,
  ProductSeasonalityDetail,
  RecommendationReviewSummaryResponse,
  RecommendationAcceptRequest,
  RecommendationConvertResponse,
  RecommendationRejectRequest,
  SeasonalProduct,
  SeasonalitySummary,
  SupplierAssignmentConfirmRequest,
  SupplierAssignmentRejectRequest,
  SupplierAssignmentReviewItem,
  SupplierAssignmentReviewSummary,
  SupplierForecastDraftRequest,
  SupplierForecastResponse,
  SupplierOption,
  UpdatePurchaseOrderLineRequest,
  WeakMapping,
} from "./types";

const AUTH_TOKEN_STORAGE_KEY = "purchasing_ai_access_token";
let unauthorizedHandler: (() => void) | null = null;

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
}

export function isAuthEnabled(): boolean {
  return import.meta.env.VITE_AUTH_ENABLED !== "false";
}

export function apiUrl(path: string, baseUrl = getApiBaseUrl()): string {
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

export function getStoredAccessToken(): string | null {
  return sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function storeAccessToken(token: string): void {
  sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAccessToken(): void {
  sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function authorizationHeaders(): Record<string, string> {
  if (!isAuthEnabled()) {
    return {};
  }
  const token = getStoredAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) {
    return null;
  }
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/^"|"$/g, ""));
  }
  const filenameMatch = header.match(/filename="?([^";]+)"?/i);
  return filenameMatch?.[1] ?? null;
}

async function fetchJson<T>(path: string, label: string, handleUnauthorized = true): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: {
      ...authorizationHeaders(),
    },
  });
  return parseJsonResponse<T>(response, label, handleUnauthorized);
}

async function sendJson<T>(
  path: string,
  label: string,
  init: RequestInit,
  handleUnauthorized = true,
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authorizationHeaders(),
      ...(init.headers ?? {}),
    },
  });
  return parseJsonResponse<T>(response, label, handleUnauthorized);
}

async function parseJsonResponse<T>(
  response: Response,
  label: string,
  handleUnauthorized = true,
): Promise<T> {
  if (!response.ok) {
    if (response.status === 401 && handleUnauthorized && isAuthEnabled()) {
      clearStoredAccessToken();
      unauthorizedHandler?.();
    }
    let detail: string | null = null;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") {
        detail = errorBody.detail;
      } else if (errorBody.detail?.message) {
        const skippedProducts = Array.isArray(errorBody.detail.skipped_products)
          ? errorBody.detail.skipped_products
              .map((product: { product_id: number; product_name: string | null; reason: string }) =>
                `${product.product_name ?? product.product_id}: ${product.reason}`,
              )
              .join("; ")
          : "";
        detail = skippedProducts
          ? `${errorBody.detail.message} Skipped products: ${skippedProducts}`
          : errorBody.detail.message;
      }
    } catch {
      detail = null;
    }
    throw new Error(detail ?? `Failed to load ${label} (${response.status})`);
  }

  return response.json();
}

async function fetchBlob(
  path: string,
  label: string,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(apiUrl(path), {
    headers: {
      ...authorizationHeaders(),
    },
  });
  if (!response.ok) {
    if (response.status === 401 && isAuthEnabled()) {
      clearStoredAccessToken();
      unauthorizedHandler?.();
    }
    let detail: string | null = null;
    try {
      const errorBody = await response.json();
      if (typeof errorBody.detail === "string") {
        detail = errorBody.detail;
      }
    } catch {
      detail = null;
    }
    throw new Error(detail ?? `Failed to load ${label} (${response.status})`);
  }
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition")),
  };
}

export async function loginAdmin(payload: LoginRequest): Promise<AuthTokenResponse> {
  const tokenResponse = await sendJson<AuthTokenResponse>(
    "/auth/login",
    "login",
    {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {},
    },
    false,
  );
  storeAccessToken(tokenResponse.access_token);
  return tokenResponse;
}

export function getCurrentAdmin(): Promise<CurrentAdmin> {
  return fetchJson<CurrentAdmin>("/auth/me", "current admin");
}

export function fetchProducts(search?: string): Promise<Product[]> {
  return fetchJson<Product[]>(`/products/${queryString({ search })}`, "products");
}

export function fetchUnmappedProducts(): Promise<Product[]> {
  return fetchJson<Product[]>("/products/unmapped", "unmapped products");
}

export function fetchWeakMappings(): Promise<WeakMapping[]> {
  return fetchJson<WeakMapping[]>("/products/weak-mappings", "weak mappings");
}

export function fetchProductSuppliers(): Promise<ProductSupplierMapping[]> {
  return fetchJson<ProductSupplierMapping[]>("/product-suppliers/", "supplier mappings");
}

export function listSuppliers(): Promise<SupplierOption[]> {
  return fetchJson<SupplierOption[]>("/suppliers", "suppliers");
}

export function fetchProductForecast(productId: number): Promise<ForecastResponse> {
  return fetchJson<ForecastResponse>(`/products/${productId}/forecast`, "product forecast");
}

export function getForecastReadinessSummary(): Promise<ForecastReadinessSummary> {
  return fetchJson<ForecastReadinessSummary>("/forecast-readiness/summary", "forecast readiness summary");
}

export function getForecastReadinessRows(filter?: string): Promise<ForecastInputAudit[]> {
  const query = filter && filter !== "all" ? `?filter=${encodeURIComponent(filter)}` : "";
  return fetchJson<ForecastInputAudit[]>(`/products/forecast-readiness${query}`, "forecast readiness");
}

export interface ForecastReconciliationQuery {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  missing_input?: string;
  supplier_id?: number;
  has_open_demand?: boolean;
  has_stock?: boolean;
  sort_by?: string;
  sort_direction?: string;
}

export function getForecastReconciliationSummary(): Promise<ForecastReconciliationSummary> {
  return fetchJson<ForecastReconciliationSummary>(
    "/api/forecast-reconciliation/summary",
    "forecast reconciliation summary",
  );
}

export function getForecastReconciliationProducts(
  query: ForecastReconciliationQuery = {},
): Promise<ForecastReconciliationProductsResponse> {
  return fetchJson<ForecastReconciliationProductsResponse>(
    `/api/forecast-reconciliation/products${queryString(query)}`,
    "forecast reconciliation products",
  );
}

export function getForecastReconciliationProduct(
  productId: number,
): Promise<ForecastReconciliationProduct> {
  return fetchJson<ForecastReconciliationProduct>(
    `/api/forecast-reconciliation/products/${productId}`,
    "forecast reconciliation product",
  );
}

export function exportForecastReconciliationCsv(
  query: ForecastReconciliationQuery = {},
): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(`/api/forecast-reconciliation/export.csv${queryString(query)}`, "forecast readiness CSV");
}

export interface DemandHistoryQuery {
  page?: number;
  page_size?: number;
  search?: string;
  has_history?: boolean;
  has_recent_demand?: boolean;
  stale_only?: boolean;
  supplier_id?: number;
  sort_by?: string;
  sort_direction?: string;
}

export function getDemandHistorySummary(): Promise<DemandHistorySummary> {
  return fetchJson<DemandHistorySummary>(
    "/api/demand-history-reconciliation/summary",
    "demand history summary",
  );
}

export function getDemandHistoryProducts(
  query: DemandHistoryQuery = {},
): Promise<DemandHistoryProductsResponse> {
  return fetchJson<DemandHistoryProductsResponse>(
    `/api/demand-history-reconciliation/products${queryString(query)}`,
    "demand history products",
  );
}

export function getDemandHistoryProduct(productId: number): Promise<DemandHistoryProduct> {
  return fetchJson<DemandHistoryProduct>(
    `/api/demand-history-reconciliation/products/${productId}`,
    "demand history product",
  );
}

export function exportDemandHistoryCsv(
  query: DemandHistoryQuery = {},
): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(`/api/demand-history-reconciliation/export.csv${queryString(query)}`, "demand coverage CSV");
}

export interface SupplierAssignmentReviewQuery {
  status?: string;
  confidence?: string;
  suggestion_source?: string;
  has_stock?: boolean;
  has_demand?: boolean;
  has_open_demand?: boolean;
  category?: string;
  brand?: string;
  supplier_id?: number;
}

export function getSupplierAssignmentReviewSummary(): Promise<SupplierAssignmentReviewSummary> {
  return fetchJson<SupplierAssignmentReviewSummary>(
    "/supplier-assignment-review/summary",
    "supplier assignment review summary",
  );
}

export function getSupplierAssignmentReviewItems(
  query: SupplierAssignmentReviewQuery = {},
): Promise<SupplierAssignmentReviewItem[]> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  });
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<SupplierAssignmentReviewItem[]>(
    `/supplier-assignment-review/items${suffix}`,
    "supplier assignment review items",
  );
}

export function confirmSupplierAssignmentReview(
  productId: number,
  payload: SupplierAssignmentConfirmRequest,
): Promise<unknown> {
  return sendJson<unknown>(
    `/products/${productId}/supplier-assignment-review/confirm`,
    "supplier assignment review",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function rejectSupplierAssignmentReview(
  productId: number,
  payload: SupplierAssignmentRejectRequest = {},
): Promise<unknown> {
  return sendJson<unknown>(
    `/products/${productId}/supplier-assignment-review/reject`,
    "supplier assignment review",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export interface ManualSupplierCleanupQuery {
  page?: number;
  page_size?: number;
  search?: string;
  priority_only?: boolean;
  sort_by?: string;
  sort_direction?: string;
  has_open_demand?: boolean;
  has_stock?: boolean;
  has_demand_history?: boolean;
  has_cost?: boolean;
  has_existing_suggestion?: boolean;
}

function queryString(query: object): string {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  });
  return params.toString() ? `?${params.toString()}` : "";
}

export function getManualSupplierCleanupSummary(): Promise<ManualSupplierCleanupSummary> {
  return fetchJson<ManualSupplierCleanupSummary>(
    "/api/manual-supplier-cleanup/summary",
    "manual supplier cleanup summary",
  );
}

export function getManualSupplierCleanupCandidates(
  query: ManualSupplierCleanupQuery = {},
): Promise<ManualSupplierCleanupCandidatesResponse> {
  return fetchJson<ManualSupplierCleanupCandidatesResponse>(
    `/api/manual-supplier-cleanup/candidates${queryString(query)}`,
    "manual supplier cleanup candidates",
  );
}

export function getManualSupplierCleanupCandidate(
  productId: number,
): Promise<ManualSupplierCleanupCandidate> {
  return fetchJson<ManualSupplierCleanupCandidate>(
    `/api/manual-supplier-cleanup/candidates/${productId}`,
    "manual supplier cleanup candidate",
  );
}

export function searchManualSupplierCleanupSuppliers(
  query: { search?: string; page?: number; page_size?: number } = {},
): Promise<ManualSupplierCleanupSuppliersResponse> {
  return fetchJson<ManualSupplierCleanupSuppliersResponse>(
    `/api/manual-supplier-cleanup/suppliers${queryString(query)}`,
    "manual supplier cleanup suppliers",
  );
}

export function assignManualSupplierCleanupCandidate(
  productId: number,
  payload: ManualSupplierCleanupAssignRequest,
): Promise<unknown> {
  return sendJson<unknown>(
    `/api/manual-supplier-cleanup/candidates/${productId}/assign`,
    "manual supplier cleanup assignment",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function reviewManualSupplierCleanupCandidate(
  productId: number,
  payload: ManualSupplierCleanupReviewRequest,
): Promise<unknown> {
  return sendJson<unknown>(
    `/api/manual-supplier-cleanup/candidates/${productId}/review`,
    "manual supplier cleanup review",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getSeasonalitySummary(month?: number): Promise<SeasonalitySummary> {
  const query = month ? `?month=${month}` : "";
  return fetchJson<SeasonalitySummary>(`/seasonality/summary${query}`, "seasonality summary");
}

export interface SeasonalProductsQuery {
  month?: number;
  status?: string;
  seasonality_tag?: string;
  supplier_id?: number;
  min_confidence?: string;
  search?: string;
  active_only?: boolean;
  sort_by?: string;
  limit?: number;
  offset?: number;
}

export function getSeasonalProducts(query: SeasonalProductsQuery = {}): Promise<SeasonalProduct[]> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  });
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<SeasonalProduct[]>(`/products/seasonal${suffix}`, "seasonal products");
}

export function getProductSeasonality(
  productId: number,
  month?: number,
): Promise<ProductSeasonalityDetail> {
  const query = month ? `?month=${month}` : "";
  return fetchJson<ProductSeasonalityDetail>(
    `/products/${productId}/seasonality${query}`,
    "product seasonality",
  );
}

export function createProductSupplier(
  payload: ProductSupplierInput,
): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>("/product-suppliers", "product supplier", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProductSupplier(
  mappingId: number,
  payload: Partial<ProductSupplierInput>,
): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>(`/product-suppliers/${mappingId}`, "product supplier", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function confirmProductSupplier(mappingId: number): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>(
    `/product-suppliers/${mappingId}/confirm`,
    "product supplier",
    { method: "POST" },
  );
}

export function rejectProductSupplier(mappingId: number): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>(
    `/product-suppliers/${mappingId}/reject`,
    "product supplier",
    { method: "POST" },
  );
}

export function setPreferredProductSupplier(mappingId: number): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>(
    `/product-suppliers/${mappingId}/set-preferred`,
    "product supplier",
    { method: "POST" },
  );
}

export function unsetPreferredProductSupplier(mappingId: number): Promise<ProductSupplierMapping> {
  return sendJson<ProductSupplierMapping>(
    `/product-suppliers/${mappingId}/unset-preferred`,
    "product supplier",
    { method: "POST" },
  );
}

export function listPurchaseOrders(): Promise<PurchaseOrder[]> {
  return fetchJson<PurchaseOrder[]>("/purchase-orders", "purchase orders");
}

export function getPurchaseOrder(poId: number): Promise<PurchaseOrder> {
  return fetchJson<PurchaseOrder>(`/purchase-orders/${poId}`, "purchase order");
}

export function getPurchaseOrderPreflight(poId: number): Promise<PurchaseOrderPreflight> {
  return fetchJson<PurchaseOrderPreflight>(`/purchase-orders/${poId}/preflight`, "purchase order preflight");
}

export function getPurchaseOrderExternalSendReadiness(
  poId: number,
): Promise<PurchaseOrderExternalSendReadiness> {
  return fetchJson<PurchaseOrderExternalSendReadiness>(
    `/purchase-orders/${poId}/external-send-readiness`,
    "purchase order external send readiness",
  );
}

export function exportPurchaseOrderCsv(
  purchaseOrderId: number,
): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(`/purchase-orders/${purchaseOrderId}/export.csv`, "purchase order CSV");
}

export function exportPurchaseOrderHandoffPacket(
  purchaseOrderId: number,
): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(`/purchase-orders/${purchaseOrderId}/handoff-packet`, "purchase order handoff packet");
}

export function createPurchaseOrder(payload: CreatePurchaseOrderRequest): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>("/purchase-orders", "purchase order", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createDraftPurchaseOrderFromProducts(
  payload: DraftFromProductsRequest,
): Promise<DraftFromProductsResponse> {
  return sendJson<DraftFromProductsResponse>(
    "/purchase-orders/draft-from-products",
    "draft purchase order",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getSupplierForecast(supplierId: number): Promise<SupplierForecastResponse> {
  return fetchJson<SupplierForecastResponse>(`/suppliers/${supplierId}/forecast`, "supplier forecast");
}

export function createDraftPOFromSupplierForecast(
  supplierId: number,
  payload: SupplierForecastDraftRequest,
): Promise<DraftFromProductsResponse> {
  return sendJson<DraftFromProductsResponse>(
    `/suppliers/${supplierId}/draft-po-from-forecast`,
    "supplier forecast draft purchase order",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function addPurchaseOrderLine(
  poId: number,
  payload: AddPurchaseOrderLineRequest,
): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/lines`, "purchase order line", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updatePurchaseOrderLine(
  poId: number,
  lineId: number,
  payload: UpdatePurchaseOrderLineRequest,
): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/lines/${lineId}`, "purchase order line", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function submitPurchaseOrderForApproval(poId: number): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(
    `/purchase-orders/${poId}/submit-for-approval`,
    "purchase order",
    { method: "POST" },
  );
}

export function approvePurchaseOrder(
  poId: number,
  payload: ApprovePurchaseOrderRequest = {},
): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/approve`, "purchase order", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function issuePurchaseOrder(poId: number): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/issue`, "purchase order", {
    method: "POST",
  });
}

export function receivePurchaseOrder(poId: number): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/receive`, "purchase order", {
    method: "POST",
  });
}

export function cancelPurchaseOrder(poId: number): Promise<PurchaseOrder> {
  return sendJson<PurchaseOrder>(`/purchase-orders/${poId}/cancel`, "purchase order", {
    method: "POST",
  });
}

export function listRecommendations(): Promise<PurchaseRecommendation[]> {
  return fetchJson<PurchaseRecommendation[]>("/recommendations", "recommendations");
}

export function getRecommendationReviewSummary(): Promise<RecommendationReviewSummaryResponse> {
  return fetchJson<RecommendationReviewSummaryResponse>(
    "/recommendations/review-summary",
    "recommendation review summary",
  );
}

export function getStaleDemandReview(decision = "all"): Promise<StaleDemandReviewResponse> {
  return fetchJson<StaleDemandReviewResponse>(
    `/recommendations/stale-demand-review${queryString({ decision })}`,
    "stale demand review",
  );
}

export function exportStaleDemandReviewCsv(): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(
    "/recommendations/stale-demand-review/export.csv?decision=all",
    "stale demand review CSV",
  );
}

export function saveStaleDemandReviewDecision(
  productId: number,
  payload: StaleDemandDecisionRequest,
): Promise<StaleDemandReviewDecision> {
  return sendJson<StaleDemandReviewDecision>(
    `/recommendations/stale-demand-review/${productId}/decision`,
    "stale demand decision",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getManagerApprovedStaleQueue(): Promise<ManagerApprovedStaleQueueResponse> {
  return fetchJson<ManagerApprovedStaleQueueResponse>(
    "/recommendations/manager-approved-stale-queue",
    "manager-approved stale queue",
  );
}

export function exportManagerApprovedStaleQueueCsv(): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(
    "/recommendations/manager-approved-stale-queue/export.csv",
    "manager-approved stale queue CSV",
  );
}

export function exportRecommendationCleanupCandidatesCsv(): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(
    "/recommendations/cleanup-candidates/export.csv",
    "recommendation cleanup candidates CSV",
  );
}

export function exportRecommendationReviewSummaryCsv(): Promise<{ blob: Blob; filename: string | null }> {
  return fetchBlob(
    "/recommendations/review-summary/export.csv",
    "recommendation review summary CSV",
  );
}

export function createManagerApprovedStaleReviewRecommendation(
  productId: number,
): Promise<PurchaseRecommendation> {
  return sendJson<PurchaseRecommendation>(
    `/recommendations/manager-approved-stale-queue/${productId}/create-review-recommendation`,
    "manager-approved stale review recommendation",
    {
      method: "POST",
      body: JSON.stringify({ created_by: "manual" }),
    },
  );
}

export function getRecommendation(recommendationId: number): Promise<PurchaseRecommendation> {
  return fetchJson<PurchaseRecommendation>(
    `/recommendations/${recommendationId}`,
    "recommendation",
  );
}

export function getRecommendationPOReadiness(recommendationId: number): Promise<RecommendationPOReadiness> {
  return fetchJson<RecommendationPOReadiness>(
    `/recommendations/${recommendationId}/po-readiness`,
    "recommendation PO readiness",
  );
}

export function createReorderRecommendation(productId: number): Promise<PurchaseRecommendation> {
  return sendJson<PurchaseRecommendation>(
    `/recommendations/reorder/${productId}`,
    "recommendation",
    { method: "POST" },
  );
}

export function acceptRecommendation(
  recommendationId: number,
  payload: RecommendationAcceptRequest = {},
): Promise<PurchaseRecommendation> {
  return sendJson<PurchaseRecommendation>(
    `/recommendations/${recommendationId}/accept`,
    "recommendation",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function rejectRecommendation(
  recommendationId: number,
  payload: RecommendationRejectRequest = {},
): Promise<PurchaseRecommendation> {
  return sendJson<PurchaseRecommendation>(
    `/recommendations/${recommendationId}/reject`,
    "recommendation",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function convertRecommendationToDraftPO(
  recommendationId: number,
): Promise<RecommendationConvertResponse> {
  return sendJson<RecommendationConvertResponse>(
    `/recommendations/${recommendationId}/convert-to-draft-po`,
    "recommendation",
    { method: "POST" },
  );
}

export function generateRecommendationLLMExplanation(
  recommendationId: number,
): Promise<RecommendationLLMExplanation> {
  return sendJson<RecommendationLLMExplanation>(
    `/recommendations/${recommendationId}/generate-llm-explanation`,
    "AI explanation",
    { method: "POST" },
  );
}
