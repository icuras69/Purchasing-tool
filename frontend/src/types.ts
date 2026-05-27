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

export interface ProductSupplierMapping {
  id: number;
  product_id: number;
  product_name: string | null;
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

export interface WeakMapping {
  product_id: number;
  product_name: string;
  reason?: string | null;
  mapping_id?: number | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_sku?: string | null;
  supplier_product_name?: string | null;
  match_status?: string | null;
  match_method?: string | null;
  match_confidence?: number | null;
}

export interface ForecastSupplierContext {
  supplier_id: number | null;
  supplier_name: string | null;
  supplier_sku: string | null;
  supplier_product_name: string | null;
  purchase_price: number | null;
  currency: string | null;
  lead_time_days: number;
  lead_time_source: string;
  minimum_order_quantity: number;
  moq_source: string;
  match_status: string | null;
  match_method: string | null;
  mapping_source: string;
  has_supplier_mapping: boolean;
  needs_supplier_mapping: boolean;
}

export interface ForecastResponse {
  product_id: number;
  product_name: string;
  current_stock: number;
  inventory_source: string;
  avg_daily_usage: number;
  days_until_stockout: number | null;
  supplier_name: string | null;
  matched_sku: string | null;
  lead_time_days_used: number;
  lead_time_source: string;
  supplier_context?: ForecastSupplierContext | null;
  reorder_point: number;
  recommended_action: string;
  recommended_qty: number;
  risk_level: string;
  explanation: string;
}
