import type { Product } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchProducts(): Promise<Product[]> {
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/products/`);
  if (!response.ok) {
    throw new Error(`Failed to load products (${response.status})`);
  }

  return response.json();
}
