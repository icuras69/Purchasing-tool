import type { Product } from "./types";

function legacySupplierName(product: Product): string | null {
  if (!product.supplier) {
    return null;
  }
  if (typeof product.supplier === "string") {
    return product.supplier;
  }
  return product.supplier.name ?? null;
}

function preferredLegacyMappingName(product: Product): string | null {
  const mappings = product.supplier_mappings ?? [];
  const preferredMapping = mappings.find((mapping) => mapping.is_preferred);
  return preferredMapping?.supplier_name ?? mappings[0]?.supplier_name ?? null;
}

export function isProductMapped(product: Product): boolean {
  return (
    (product.supplier_id !== null && product.supplier_id !== undefined) ||
    (product.preferred_supplier_id !== null && product.preferred_supplier_id !== undefined) ||
    product.mapping_status === "mapped"
  );
}

export function supplierDisplayName(product: Product): string {
  if (product.supplier_name) {
    return product.supplier_name;
  }

  if (product.preferred_supplier) {
    return product.preferred_supplier;
  }

  const legacySupplier = legacySupplierName(product);
  if (legacySupplier) {
    return `${legacySupplier} (legacy)`;
  }

  const mappingName = preferredLegacyMappingName(product);
  if (mappingName) {
    return mappingName;
  }

  return "No supplier assigned";
}

export function productMatchesQuery(product: Product, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  const supplierNames = (product.supplier_mappings ?? [])
    .map((mapping) => mapping.supplier_name ?? "")
    .join(" ");

  return `${product.id} ${product.name} ${product.description ?? ""} ${product.orderpro_sku ?? ""} ${product.barcode ?? ""} ${product.supplier_sku ?? ""} ${product.supplier_code ?? ""} ${supplierDisplayName(product)} ${supplierNames}`
    .toLowerCase()
    .includes(normalized);
}

export function filterProductsByQuery(products: Product[], query: string): Product[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return products;
  }

  if (/^\d+$/.test(normalized)) {
    const exactIdMatches = products.filter((product) => String(product.id) === normalized);
    if (exactIdMatches.length > 0) {
      return exactIdMatches;
    }
  }

  return products.filter((product) => productMatchesQuery(product, query));
}
