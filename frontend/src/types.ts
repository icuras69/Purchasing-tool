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
  orderpro_sku?: string | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  supplier_code?: string | null;
  supplier_sku?: string | null;
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

export interface SupplierOption {
  id: number;
  name: string;
  orderpro_id: string | null;
  orderpro_code: string | null;
  is_active: boolean;
  lead_time_days: number | null;
}

export interface SupplierAssignmentReviewSummary {
  total_orderpro_products: number;
  missing_supplier_products: number;
  missing_supplier_products_with_stock: number;
  missing_supplier_products_with_demand_history: number;
  missing_supplier_products_with_open_customer_demand: number;
  missing_supplier_products_with_seasonality_profile: number;
  missing_supplier_products_with_po_supplier_evidence: number;
  missing_supplier_products_with_no_evidence: number;
  suggested_supplier_count_by_confidence: Record<string, number>;
  suggestion_count_by_source: Record<string, number>;
  review_status_counts: Record<string, number>;
  no_suggestion_count: number;
  top_categories_affected: Record<string, number>;
  top_brands_affected: Record<string, number>;
}

export interface SupplierAssignmentReviewItem {
  product_id: number;
  orderpro_id: string | null;
  orderpro_sku: string | null;
  name: string;
  barcode: string | null;
  brand: string | null;
  category: string | null;
  current_stock: number | null;
  demand_history_available: boolean;
  open_customer_demand: number;
  seasonality_tag: string | null;
  cost_source: string | null;
  lead_time_status: string;
  suggested_supplier_id: number | null;
  suggested_supplier_name: string | null;
  suggestion_source: string | null;
  confidence_label: string;
  confidence_score: number;
  evidence_summary: Record<string, unknown> | null;
  evidence_date: string | null;
  warnings: string[];
  status: string;
  review_id: number | null;
  reviewed_supplier_id: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface SupplierAssignmentConfirmRequest {
  supplier_id: number;
  reviewed_by?: string | null;
  note?: string | null;
}

export interface SupplierAssignmentRejectRequest {
  reason?: string | null;
  reviewed_by?: string | null;
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
  supplier_code?: string | null;
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

export interface IncomingStockContext {
  product_id: number;
  incoming_qty: number;
  incoming_qty_local?: number;
  incoming_qty_orderpro?: number;
  incoming_qty_total?: number;
  incoming_qty_by_source: Record<string, number>;
  source_breakdown: Record<string, { incoming_qty?: number; open_po_line_count?: number }>;
  open_po_count: number;
  open_po_line_count: number;
  earliest_expected_date: string | null;
  latest_expected_date: string | null;
  supplier_ids: number[];
  warnings: string[];
}

export interface ForecastResponse {
  product_id: number;
  product_name: string;
  orderpro_sku?: string | null;
  current_stock: number;
  inventory_source: string;
  avg_daily_usage: number;
  demand_source?: string | null;
  demand_lookback_days?: number | null;
  demand_history_start?: string | null;
  demand_history_end?: string | null;
  observation_days?: number | null;
  shipped_units_in_window?: number | null;
  shipped_order_count?: number | null;
  open_confirmed_units?: number | null;
  open_packed_units?: number | null;
  open_backorder_units?: number | null;
  total_open_demand?: number | null;
  effective_available_stock?: number | null;
  net_available_stock?: number | null;
  projected_lead_time_demand?: number | null;
  total_required_stock?: number | null;
  incoming_qty?: number | null;
  effective_available_stock_for_reorder?: number | null;
  recommended_qty_before_inbound?: number | null;
  recommended_qty_after_inbound?: number | null;
  inbound_adjustment_qty?: number | null;
  units_sold_in_window?: number | null;
  eligible_order_count?: number | null;
  excluded_order_count?: number | null;
  days_until_stockout: number | null;
  supplier_name: string | null;
  matched_sku: string | null;
  lead_time_days_used: number;
  lead_time_source: string;
  supplier_context?: ForecastSupplierContext | null;
  incoming_stock_context?: IncomingStockContext | null;
  forecast_input_context?: ForecastInputContext | null;
  cost_price?: number | null;
  cost_source?: string | null;
  cost_confidence?: string | null;
  estimated_unit_cost?: number | null;
  estimated_cost_source?: string | null;
  estimated_purchase_value?: number | null;
  moq_source?: string | null;
  pack_size?: number | null;
  pack_size_source?: string | null;
  safety_stock_used?: number | null;
  safety_stock_source?: string | null;
  input_blocking_issues?: string[];
  input_warning_issues?: string[];
  forecast_readiness_score?: number | null;
  reorder_point: number;
  recommended_action: string;
  recommended_qty: number;
  risk_level: string;
  explanation: string;
  seasonality_context?: ForecastSeasonalityContext | null;
}

export interface ForecastReadinessSummary {
  product_count: number;
  products_with_complete_critical_inputs: number;
  products_missing_supplier: number;
  products_missing_lead_time: number;
  products_missing_cost: number;
  products_missing_moq?: number;
  products_missing_pack_size?: number;
  products_using_fallback_moq?: number;
  products_using_po_derived_cost?: number;
  products_using_orderpro_cost?: number;
  suppliers_missing_lead_time?: number;
  products_blocked_by_missing_supplier?: number;
  products_blocked_by_missing_demand?: number;
  products_complete_before_reconciliation?: number;
  products_complete_after_reconciliation?: number;
  products_missing_demand_history: number;
  products_missing_seasonality: number;
  products_with_validated_seasonality: number;
  products_with_harmful_seasonality: number;
}

export interface ForecastInputContext {
  product_id: number;
  cost_price: number | null;
  cost_source: string;
  cost_confidence: string;
  lead_time_days: number | null;
  lead_time_source: string;
  lead_time_confidence: string;
  min_order_qty: number | null;
  moq_source: string;
  pack_size: number | null;
  pack_size_source: string;
  safety_stock: number | null;
  safety_stock_source: string;
  blocking_issues: string[];
  warning_issues: string[];
  readiness_score: number;
}

export interface ForecastInputAudit {
  product_id: number;
  orderpro_sku: string | null;
  product_name: string;
  available_inputs?: string[];
  missing_inputs?: string[];
  inputs_currently_used?: string[];
  advisory_inputs?: string[];
  blocking_issues: string[];
  warning_issues: string[];
  forecast_readiness_score?: number;
  readiness_score?: number;
  cost_price: number | null;
  cost_source: string;
  cost_confidence: string;
  lead_time_days: number | null;
  lead_time_source: string;
  lead_time_confidence: string;
  min_order_qty: number | null;
  moq_source: string;
  pack_size: number | null;
  pack_size_source: string;
  safety_stock: number | null;
  safety_stock_source: string;
  seasonality_activation_recommendation?: string;
  seasonality_readiness_status?: string | null;
  forecast_recommended_qty?: number;
  supplier_assignment_suggestion?: {
    suggested_supplier_id: number;
    suggested_supplier_name: string | null;
    suggestion_source: string | null;
    confidence_label: string;
    confidence_score: number;
  } | null;
}

export type SeasonalityStatus =
  | "in_season"
  | "approaching_season"
  | "off_season"
  | "year_round"
  | "insufficient_data"
  | string;

export type SeasonalityTag =
  | "winter"
  | "spring"
  | "summer"
  | "autumn"
  | "multi_peak"
  | "year_round"
  | "insufficient_data"
  | string;

export type SeasonalityConfidence = "high" | "medium" | "low" | "insufficient" | string;

export interface ForecastSeasonalityContext {
  seasonality_tag: SeasonalityTag | null;
  current_status: SeasonalityStatus;
  selected_month_index: number | null;
  primary_season: string | null;
  peak_months: number[];
  confidence_score: number | null;
  confidence_label: SeasonalityConfidence | null;
  advisory_message: string;
}

export interface SeasonalitySummary {
  classification_counts: Record<string, number>;
  confidence_counts: Record<string, number>;
  current_season_counts: Record<string, number>;
  profile_count: number;
  product_count: number;
  missing_profile_count: number;
  selected_month: number;
  include_legacy?: boolean;
}

export interface SeasonalProduct {
  product_id: number;
  orderpro_sku: string | null;
  name: string;
  supplier_id: number | null;
  supplier_name: string | null;
  current_stock: number;
  seasonality_tag: SeasonalityTag | null;
  current_seasonality_status: SeasonalityStatus;
  selected_month: number;
  selected_month_units: number | null;
  selected_month_index: number | null;
  peak_months: number[];
  primary_season: string | null;
  seasonality_strength: number | null;
  confidence_score: number | null;
  confidence_label: SeasonalityConfidence | null;
  history_start: string | null;
  history_end: string | null;
  years_covered: number | null;
}

export interface SeasonalityInterpretation {
  current_status: SeasonalityStatus;
  selected_month: number;
  selected_month_units: number | null;
  selected_month_index: number | null;
  advisory_message: string;
}

export interface ProductSeasonalityDetail {
  product_id: number;
  orderpro_sku: string | null;
  name: string;
  history_start: string | null;
  history_end: string | null;
  history_months: number;
  active_months: number;
  years_covered: number;
  total_units: number;
  average_monthly_units: number;
  monthly_units: Record<string, number> | null;
  monthly_indices: Record<string, number> | null;
  peak_months: number[];
  low_months: number[];
  primary_season: string | null;
  seasonality_tag: SeasonalityTag;
  seasonality_strength: number;
  confidence_score: number;
  confidence_label: SeasonalityConfidence;
  coefficient_of_variation: number | null;
  calculation_version: string;
  calculated_at: string;
  current_interpretation: SeasonalityInterpretation;
  direct_history_row_count: number;
  linked_history_row_count: number;
  contributing_historical_product_ids: number[];
  reconciliation_methods: string[];
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
  product_supplier_id: number | null;
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
  product_supplier_id?: number | null;
  product_id?: number | null;
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
  supplier_id?: number | null;
  product_ids: number[];
  created_by?: string | null;
  notes?: string | null;
  only_reorder_needed?: boolean;
}

export interface DraftFromProductsSkippedProduct {
  product_id: number;
  product_name: string | null;
  reason: string;
}

export interface DraftFromProductsResponse {
  purchase_order: PurchaseOrder | null;
  created_purchase_orders: PurchaseOrder[];
  summary: {
    created_po_count: number | null;
    created_line_count: number;
    skipped_products: DraftFromProductsSkippedProduct[];
    grouped_by_supplier: Record<string, number> | null;
  };
}

export interface SupplierForecastResponse {
  supplier_id: number;
  supplier_name: string | null;
  product_count: number;
  forecasts: ForecastResponse[];
  products_needing_reorder: number[];
  products_missing_data: number[];
  total_recommended_quantity: number;
  total_estimated_cost: number | null;
}

export interface SupplierForecastDraftRequest {
  created_by?: string | null;
  notes?: string | null;
  only_reorder_needed?: boolean;
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

export interface RecommendationLLMExplanation {
  suggested_action: string;
  summary: string;
  explanation: string;
  risk_flags: string[];
  missing_data_warnings: string[];
  confidence: number;
  structured_data_citations: string[];
  model_name: string;
  prompt_version: string;
}
