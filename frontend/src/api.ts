import type {
  ForecastResponse,
  AddPurchaseOrderLineRequest,
  ApprovePurchaseOrderRequest,
  CreatePurchaseOrderRequest,
  Product,
  ProductSupplierInput,
  ProductSupplierMapping,
  PurchaseOrder,
  UpdatePurchaseOrderLineRequest,
  WeakMapping,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

async function fetchJson<T>(path: string, label: string): Promise<T> {
  const response = await fetch(apiUrl(path));
  return parseJsonResponse<T>(response, label);
}

async function sendJson<T>(
  path: string,
  label: string,
  init: RequestInit,
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  return parseJsonResponse<T>(response, label);
}

async function parseJsonResponse<T>(response: Response, label: string): Promise<T> {
  if (!response.ok) {
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

  return response.json();
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

export function fetchProductForecast(productId: number): Promise<ForecastResponse> {
  return fetchJson<ForecastResponse>(`/products/${productId}/forecast`, "product forecast");
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
