export type MappingStatus = "mapped" | "unmapped" | string;

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: "bearer" | string;
  expires_in: number;
}

export interface CurrentAdmin {
  email: string;
  role: "admin" | string;
}

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
  supplier: string | { name?: string | null } | null;
  description?: string | null;
  barcode?: string | null;
  orderpro_sku?: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  supplier_code: string | null;
  supplier_sku?: string | null;
  current_stock: number | null;
  supplier_count?: number;
  preferred_supplier?: string | null;
  preferred_supplier_id?: number | null;
  preferred_supplier_sku?: string | null;
  supplier_mappings?: SupplierMapping[];
  mapping_status?: MappingStatus | null;
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

export interface ManualSupplierCleanupSummary {
  total_products: number;
  products_with_supplier: number;
  products_missing_supplier: number;
  priority_missing_supplier_products: number;
  confirmed_manual_assignments: number;
  deferred_reviews: number;
  rejected_reviews: number;
  needs_information_reviews: number;
  completion_percentage: number;
}

export interface ManualSupplierCleanupCandidate {
  product_id: number;
  orderpro_id: string | null;
  orderpro_sku: string | null;
  product_name: string;
  barcode: string | null;
  brand: string | null;
  category: string | null;
  description?: string | null;
  current_stock: number;
  demand_history_available: boolean;
  open_customer_demand: number;
  seasonality_tag: string | null;
  cost_price: number | null;
  cost_source: string | null;
  lead_time_status: string;
  forecast_readiness_score: number | null;
  blocking_issues: string[];
  warning_issues: string[];
  existing_suggested_supplier_id: number | null;
  existing_suggested_supplier_name: string | null;
  existing_suggestion_source: string | null;
  existing_confidence_label: string;
  evidence_summary: Record<string, unknown> | null;
  review_status: string;
  priority_score: number;
  priority_reason: string;
  suggested_action: string;
  review?: Record<string, unknown> | null;
}

export interface ManualSupplierCleanupCandidatesResponse {
  items: ManualSupplierCleanupCandidate[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  summary: {
    total_missing_supplier: number;
    priority_candidates: number;
    with_open_demand: number;
    with_stock: number;
    with_demand_history: number;
    with_cost: number;
  };
}

export interface ManualSupplierCleanupSupplier extends SupplierOption {
  assigned_product_count: number;
}

export interface ManualSupplierCleanupSuppliersResponse {
  items: ManualSupplierCleanupSupplier[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ManualSupplierCleanupAssignRequest {
  supplier_id: number;
  reviewed_by?: string | null;
  notes?: string | null;
}

export interface ManualSupplierCleanupReviewRequest {
  status: "deferred" | "rejected" | "needs_information" | string;
  reviewed_by?: string | null;
  notes?: string | null;
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

export interface PackRuleContext {
  raw_required_quantity: number;
  pre_pack_quantity: number;
  final_quantity: number;
  order_multiple: number;
  rule_id: number | null;
  rule_name: string;
  rule_source: string;
  pack_type?: string | null;
  units_per_box?: number | null;
  units_per_pallet?: number | null;
  pallet_only?: boolean;
  display: string;
  explanation: string;
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
  raw_required_quantity?: number | null;
  pre_pack_recommended_quantity?: number | null;
  order_multiple?: number | null;
  pack_rule_id?: number | null;
  pack_rule_name?: string | null;
  pack_rule_source?: string | null;
  pack_rule_display?: string | null;
  pack_rounding_explanation?: string | null;
  pack_rule_warnings?: string[];
  pack_rule_context?: PackRuleContext | null;
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

export interface ForecastReconciliationSummary {
  total_products: number;
  ready: number;
  partially_ready: number;
  blocked: number;
  monitor_only: number;
  missing_supplier: number;
  missing_lead_time: number;
  missing_cost: number;
  missing_pack_size: number;
  missing_demand_history: number;
  missing_stock: number;
  readiness_percentage: number;
}

export interface ForecastReconciliationProduct {
  product_id: number;
  sku: string | null;
  orderpro_sku: string | null;
  product_name: string;
  description: string | null;
  barcode: string | null;
  supplier_id: number | null;
  supplier_code: string | null;
  supplier_name: string | null;
  supplier_source: string;
  current_stock: number | null;
  stock_source: string;
  demand_history_available: boolean;
  demand_source: string;
  open_customer_demand: number;
  lead_time_days: number | null;
  lead_time_source: string;
  cost_price: number | null;
  cost_source: string;
  pack_size: number | null;
  pack_size_source: string;
  min_order_qty: number | null;
  moq_source: string;
  seasonality_status: string;
  readiness_score: number;
  readiness_status: "ready" | "partially_ready" | "blocked" | "monitor_only" | string;
  missing_inputs: string[];
  warnings: string[];
  blocking_issues: string[];
  recommendation_status: string | null;
  recommended_quantity: number | null;
  explanation: string;
  sources: Record<string, string>;
  inputs?: Record<string, {
    value: string | number | boolean | null;
    supplier_id?: number | null;
    source: string;
    is_missing: boolean;
    is_fallback: boolean;
    blocks_forecast: boolean;
    warning?: string | null;
  }>;
}

export interface ForecastReconciliationProductsResponse {
  items: ForecastReconciliationProduct[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  summary: ForecastReconciliationSummary;
}

export interface DemandHistorySummary {
  total_products: number;
  products_with_demand_history: number;
  products_without_demand_history: number;
  products_with_recent_demand: number;
  products_with_stale_demand: number;
  total_demand_rows: number;
  earliest_demand_date: string | null;
  latest_demand_date: string | null;
  coverage_percentage: number;
  products_blocked_by_missing_demand_history: number;
  selected_date: string;
}

export interface DemandHistoryProduct {
  product_id: number;
  sku: string | null;
  orderpro_sku: string | null;
  barcode: string | null;
  description: string | null;
  product_name: string;
  supplier_id: number | null;
  supplier_code: string | null;
  supplier_name: string | null;
  current_stock: number | null;
  has_demand_history: boolean;
  demand_row_count: number;
  earliest_demand_date: string | null;
  latest_demand_date: string | null;
  months_covered: number;
  total_units: number;
  units_last_30_days: number;
  units_last_90_days: number;
  average_monthly_units: number;
  return_units: number;
  stale_demand: boolean;
  gap_warnings: string[];
  readiness_status: string;
  readiness_score: number;
  readiness_missing_inputs?: string[];
  demand_source: string;
  monthly_buckets?: Array<{ month: string; net_units: number; return_units: number }>;
  source_systems?: string[];
  readiness_impact?: string;
  current_forecast_demand_source?: string;
}

export interface DemandHistoryProductsResponse {
  items: DemandHistoryProduct[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
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

export interface PurchaseOrderPreflightLineCheck {
  line_id: number | null;
  product_id: number | null;
  product_name: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  quantity: number | null;
  unit_cost: number | null;
  estimated_line_total: number | null;
  product_supplier_id: number | null;
  source_recommendation_id: number | null;
  is_inventory_product: boolean | null;
  canonical_supplier_matches_po_supplier: boolean | null;
  quantity_valid: boolean;
  cost_present: boolean;
  supplier_snapshot_present: boolean;
  blockers: string[];
  warnings: string[];
}

export interface PurchaseOrderPreflight {
  purchase_order_id: number;
  status: string;
  supplier_id: number | null;
  supplier_name: string | null;
  can_submit: boolean;
  can_approve: boolean;
  can_issue_if_applicable: boolean;
  overall_status: "ready" | "needs_review" | "blocked" | string;
  blockers: string[];
  warnings: string[];
  line_checks: PurchaseOrderPreflightLineCheck[];
  summary_counts: {
    line_count: number;
    blocker_count: number;
    warning_count: number;
    lines_with_blockers: number;
    lines_with_warnings: number;
  };
}

export interface PurchaseOrderExternalSendReadiness {
  purchase_order_id: number;
  status: string;
  supplier_id: number | null;
  supplier_name: string | null;
  can_send_externally: boolean;
  external_send_supported: boolean;
  external_send_system: string;
  blockers: string[];
  warnings: string[];
  required_local_status: string;
  preflight_summary: {
    overall_status: string;
    can_submit: boolean;
    can_approve: boolean;
    can_issue_if_applicable: boolean;
    blocker_count: number;
    warning_count: number;
    line_count: number;
    blockers: string[];
    warnings: string[];
  };
  message: string;
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

export interface RecommendationPOReadiness {
  recommendation_id: number;
  product_id: number;
  product_name: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  recommendation_status: string;
  recommendation_type: string;
  recommended_quantity: number;
  estimated_unit_cost: number | null;
  estimated_total_cost: number | null;
  can_create_draft_po: boolean;
  blockers: string[];
  warnings: string[];
  required_manager_decision: string | null;
  po_supplier_source: string;
  canonical_supplier_check_result: string;
  product_supplier_id: number | null;
  recommendation_supplier_id: number | null;
  forecast_recommended_action: string | null;
  stale_demand_only: boolean;
  review_decision: string | null;
  purchase_readiness_status: string | null;
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

export interface StaleDemandReviewItem {
  product_id: number;
  product_name: string | null;
  orderpro_sku: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  last_demand_date: string | null;
  days_since_last_demand: number | null;
  demand_rows: number;
  monthly_average_demand: number;
  current_stock: number | null;
  lead_time_days: number | null;
  advisory_recommended_quantity: number;
  estimated_unit_cost: number | null;
  estimated_total_cost: number | null;
  blockers: string[];
  warnings: string[];
  purchase_readiness_issues: string[];
  suggested_action: string;
  stale_demand_policy: string | null;
  review_decision: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  decision_status: string;
  recommendation_status: string | null;
  purchase_readiness_status: string | null;
}

export interface StaleDemandReviewResponse {
  summary: {
    products_evaluated: number;
    total_candidates: number;
    suggested_action_counts: Record<string, number>;
    skipped_counts: Record<string, number>;
    limit: number;
    decision_filter?: string;
  };
  items: StaleDemandReviewItem[];
}

export interface StaleDemandDecisionRequest {
  decision: string;
  reviewed_by: string;
  notes?: string | null;
}

export interface StaleDemandReviewDecision {
  id: number;
  product_id: number;
  product_name: string | null;
  orderpro_sku: string | null;
  recommendation_id: number | null;
  decision: string;
  reviewed_by: string;
  notes: string | null;
  reviewed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ManagerApprovedStaleQueueItem {
  product_id: number;
  product_name: string | null;
  orderpro_sku: string | null;
  supplier_id: number | null;
  supplier_name: string | null;
  lead_time_days: number | null;
  current_stock: number | null;
  last_demand_date: string | null;
  days_since_last_demand: number | null;
  advisory_recommended_quantity: number;
  estimated_unit_cost: number | null;
  estimated_total_cost: number | null;
  reviewed_by: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  review_decision: string | null;
  safety_status: string;
  safety_blockers: string[];
  warnings: string[];
  suggested_next_action: string;
  recommendation_status: string | null;
  purchase_readiness_status: string | null;
}

export interface ManagerApprovedStaleQueueResponse {
  summary: {
    decisions_evaluated: number;
    total_candidates: number;
    safety_status_counts: Record<string, number>;
    suggested_next_action_counts: Record<string, number>;
    limit: number;
  };
  items: ManagerApprovedStaleQueueItem[];
}

export interface RecommendationReviewSummaryResponse {
  summary: {
    total_existing_recommendations: number;
    pending_review_recommendations: number;
    accepted_recommendations: number;
    rejected_recommendations: number;
    recommendation_status_counts: Record<string, number>;
    stale_demand_candidates: number;
    stale_demand_decisions_by_type: Record<string, number>;
    manager_approved_stale_queue_count: number;
    manager_approved_stale_queue_by_safety_status: Record<string, number>;
    cleanup_candidates_count: number;
    cleanup_candidates_by_issue: Record<string, number>;
    recommendations_ready_for_manual_review: number;
    recommendations_blocked_from_po_conversion: number;
    limit: number;
  };
}
