import type { Product } from "./types";

export function supplierDisplayName(product: Product): string {
  if (product.supplier_name) {
    return product.supplier_code
      ? `${product.supplier_name} (${product.supplier_code})`
      : product.supplier_name;
  }

  if (product.mapping_status === "mapped" && product.preferred_supplier) {
    return product.preferred_supplier;
  }

  const firstMapping = product.supplier_mappings?.[0];
  if (firstMapping?.supplier_name) {
    return firstMapping.supplier_name;
  }

  if (product.supplier) {
    return `${product.supplier} (legacy)`;
  }

  return "Unmapped";
}

export function productMatchesQuery(product: Product, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  const supplierNames = product.supplier_mappings
    .map((mapping) => mapping.supplier_name ?? "")
    .join(" ");

  return `${product.name} ${product.orderpro_sku ?? ""} ${product.supplier_sku ?? ""} ${supplierDisplayName(product)} ${supplierNames}`
    .toLowerCase()
    .includes(normalized);
}
