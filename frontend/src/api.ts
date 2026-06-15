import type {
  ForecastResponse,
  ForecastInputAudit,
  ForecastReadinessSummary,
  AddPurchaseOrderLineRequest,
  ApprovePurchaseOrderRequest,
  AuthTokenResponse,
  CurrentAdmin,
  CreatePurchaseOrderRequest,
  DraftFromProductsRequest,
  DraftFromProductsResponse,
  LoginRequest,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  PurchaseOrder,
  PurchaseRecommendation,
  RecommendationLLMExplanation,
  ProductSeasonalityDetail,
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
  const token = getStoredAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
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
    if (response.status === 401 && handleUnauthorized) {
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

export function fetchProducts(): Promise<Product[]> {
  return fetchJson<Product[]>("/products/", "products");
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

export function getRecommendation(recommendationId: number): Promise<PurchaseRecommendation> {
  return fetchJson<PurchaseRecommendation>(
    `/recommendations/${recommendationId}`,
    "recommendation",
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
