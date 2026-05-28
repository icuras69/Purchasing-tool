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

export interface ProductSupplierInput {
  product_id: number;
  supplier_id: number;
  supplier_sku?: string | null;
  supplier_product_name?: string | null;
  purchase_price?: number | null;
  currency?: string | null;
  minimum_order_quantity?: number | null;
  pack_size?: number | null;
  lead_time_days?: number | null;
  match_status?: string | null;
  match_method?: string | null;
  match_confidence?: number | null;
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

export type PurchaseOrderStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "issued"
  | "received"
  | "cancelled"
  | string;

export interface PurchaseOrderLine {
  id: number;
  purchase_order_id: number;
  product_id: number;
  product_name?: string | null;
  product_supplier_id: number;
  supplier_sku: string | null;
  supplier_product_name: string | null;
  quantity: number;
  unit_cost: number | null;
  currency: string | null;
  line_total: number | null;
  minimum_order_quantity: number | null;
  pack_size: number | null;
  lead_time_days: number | null;
  notes: string | null;
}

export interface PurchaseOrder {
  id: number;
  supplier_id: number | null;
  supplier_name: string | null;
  status: PurchaseOrderStatus;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  issued_at: string | null;
  received_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  total_amount: number | null;
  currency: string | null;
  created_by: string | null;
  approved_by: string | null;
  lines: PurchaseOrderLine[];
}

export interface CreatePurchaseOrderRequest {
  supplier_id: number;
  notes?: string | null;
  created_by?: string | null;
}

export interface AddPurchaseOrderLineRequest {
  product_supplier_id: number;
  quantity: number;
  notes?: string | null;
}

export interface UpdatePurchaseOrderLineRequest {
  quantity?: number | null;
  notes?: string | null;
}

export interface ApprovePurchaseOrderRequest {
  approved_by?: string | null;
}

export interface DraftFromProductsRequest {
  supplier_id: number;
  product_ids: number[];
  created_by?: string | null;
  notes?: string | null;
}

export interface DraftFromProductsSkippedProduct {
  product_id: number;
  product_name: string | null;
  reason: string;
}

export interface DraftFromProductsResponse {
  purchase_order: PurchaseOrder;
  summary: {
    created_line_count: number;
    skipped_products: DraftFromProductsSkippedProduct[];
  };
}

export type RecommendationStatus =
  | "draft"
  | "pending_review"
  | "accepted"
  | "rejected"
  | "converted_to_po"
  | string;

export interface PurchaseRecommendation {
  id: number;
  product_id: number;
  product_name: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  product_supplier_id: number | null;
  converted_purchase_order_id: number | null;
  recommendation_type: string;
  status: RecommendationStatus;
  recommended_quantity: number;
  recommended_supplier_name: string | null;
  recommended_supplier_sku: string | null;
  estimated_unit_cost: number | null;
  estimated_total_cost: number | null;
  currency: string | null;
  reason: string | null;
  confidence: number | null;
  input_snapshot: Record<string, unknown> | null;
  forecast_snapshot: Record<string, unknown> | null;
  supplier_context_snapshot: Record<string, unknown> | null;
  model_name: string | null;
  prompt_version: string | null;
  generated_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejected_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecommendationAcceptRequest {
  reviewed_by?: string | null;
}

export interface RecommendationRejectRequest {
  rejected_reason?: string | null;
  reviewed_by?: string | null;
}

export interface RecommendationConvertResponse {
  recommendation: PurchaseRecommendation;
  purchase_order: PurchaseOrder;
}
