import type { ForecastResponse, Product, ProductSupplierMapping, WeakMapping } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

async function fetchJson<T>(path: string, label: string): Promise<T> {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    throw new Error(`Failed to load ${label} (${response.status})`);
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
