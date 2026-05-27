export type MappingStatus = "mapped" | "unmapped" | string;

export interface SupplierMapping {
  id: number;
  supplier_id: number;
  supplier_name: string | null;
  supplier_sku: string | null;
  supplier_product_name: string | null;
  purchase_price: number | null;
  currency: string | null;
  minimum_order_quantity: number | null;
  pack_size: number | null;
  lead_time_days: number | null;
  is_preferred: boolean;
  match_status: string | null;
  match_method: string | null;
  match_confidence: number | null;
  last_synced_at: string | null;
}

export interface Product {
  id: number;
  name: string;
  supplier: string | null;
  current_stock: number | null;
  supplier_count: number;
  preferred_supplier: string | null;
  preferred_supplier_id: number | null;
  preferred_supplier_sku: string | null;
  supplier_mappings: SupplierMapping[];
  mapping_status: MappingStatus;
}
