import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  confirmProductSupplier,
  confirmSupplierAssignmentReview,
  addPurchaseOrderLine,
  assignManualSupplierCleanupCandidate,
  acceptRecommendation,
  approvePurchaseOrder,
  cancelPurchaseOrder,
  convertRecommendationToDraftPO,
  createManagerApprovedStaleReviewRecommendation,
  createDraftPOFromSupplierForecast,
  createDraftPurchaseOrderFromProducts,
  createPurchaseOrder,
  createProductSupplier,
  createReorderRecommendation,
  exportManagerApprovedStaleQueueCsv,
  exportPurchaseOrderHandoffPacket,
  exportPurchaseOrderCsv,
  exportRecommendationCleanupCandidatesCsv,
  exportRecommendationReviewSummaryCsv,
  exportStaleDemandReviewCsv,
  fetchProductForecast,
  fetchProductSuppliers,
  fetchProducts,
  fetchUnmappedProducts,
  fetchWeakMappings,
  generateRecommendationLLMExplanation,
  clearStoredAccessToken,
  getCurrentAdmin,
  getForecastReadinessRows,
  getForecastReadinessSummary,
  getForecastReconciliationProduct,
  getForecastReconciliationProducts,
  getForecastReconciliationSummary,
  exportForecastReconciliationCsv,
  getDemandHistoryProduct,
  getDemandHistoryProducts,
  getDemandHistorySummary,
  exportDemandHistoryCsv,
  getManualSupplierCleanupCandidate,
  getManualSupplierCleanupCandidates,
  getManualSupplierCleanupSummary,
  getManagerApprovedStaleQueue,
  getStoredAccessToken,
  getSupplierAssignmentReviewItems,
  getSupplierAssignmentReviewSummary,
  getProductSeasonality,
  getSeasonalProducts,
  getSeasonalitySummary,
  getStaleDemandReview,
  getSupplierForecast,
  getPurchaseOrder,
  getPurchaseOrderExternalSendReadiness,
  getPurchaseOrderPreflight,
  getRecommendation,
  getRecommendationPOReadiness,
  getRecommendationReviewSummary,
  isAuthEnabled,
  issuePurchaseOrder,
  loginAdmin,
  listRecommendations,
  listPurchaseOrders,
  listSupplierRecords,
  listSuppliers,
  receivePurchaseOrder,
  refreshOrderProInventory,
  rejectRecommendation,
  rejectProductSupplier,
  rejectSupplierAssignmentReview,
  reviewManualSupplierCleanupCandidate,
  saveStaleDemandReviewDecision,
  searchManualSupplierCleanupSuppliers,
  setPreferredProductSupplier,
  setUnauthorizedHandler,
  submitPurchaseOrderForApproval,
  unsetPreferredProductSupplier,
  updateSupplier,
} from "./api";
import type {
  ForecastResponse,
  ForecastInputAudit,
  ForecastReadinessSummary,
  ForecastReconciliationProduct,
  ForecastReconciliationSummary,
  DemandHistoryProduct,
  DemandHistorySummary,
  ManualSupplierCleanupCandidate,
  ManualSupplierCleanupSummary,
  ManualSupplierCleanupSupplier,
  ManagerApprovedStaleQueueResponse,
  ProductSeasonalityDetail,
  Product,
  ProductSupplierMapping,
  PurchaseOrder,
  PurchaseOrderExternalSendReadiness,
  PurchaseOrderPreflight,
  PurchaseRecommendation,
  RecommendationPOReadiness,
  RecommendationLLMExplanation,
  RecommendationReviewSummaryResponse,
  SeasonalProduct,
  SeasonalitySummary,
  StaleDemandReviewResponse,
  SupplierAssignmentReviewItem,
  SupplierAssignmentReviewSummary,
  SupplierForecastResponse,
  SupplierOption,
  SupplierRecord,
  WeakMapping,
} from "./types";

vi.mock("./api", () => ({
  fetchProducts: vi.fn(),
  fetchUnmappedProducts: vi.fn(),
  fetchWeakMappings: vi.fn(),
  fetchProductSuppliers: vi.fn(),
  fetchProductForecast: vi.fn(),
  getStoredAccessToken: vi.fn(),
  clearStoredAccessToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
  loginAdmin: vi.fn(),
  getCurrentAdmin: vi.fn(),
  generateRecommendationLLMExplanation: vi.fn(),
  getForecastReadinessSummary: vi.fn(),
  getForecastReadinessRows: vi.fn(),
  getForecastReconciliationSummary: vi.fn(),
  getForecastReconciliationProducts: vi.fn(),
  getForecastReconciliationProduct: vi.fn(),
  exportForecastReconciliationCsv: vi.fn(),
  getDemandHistorySummary: vi.fn(),
  getDemandHistoryProducts: vi.fn(),
  getDemandHistoryProduct: vi.fn(),
  exportDemandHistoryCsv: vi.fn(),
  getSupplierAssignmentReviewSummary: vi.fn(),
  getSupplierAssignmentReviewItems: vi.fn(),
  getManualSupplierCleanupSummary: vi.fn(),
  getManualSupplierCleanupCandidates: vi.fn(),
  getManualSupplierCleanupCandidate: vi.fn(),
  searchManualSupplierCleanupSuppliers: vi.fn(),
  assignManualSupplierCleanupCandidate: vi.fn(),
  reviewManualSupplierCleanupCandidate: vi.fn(),
  listSuppliers: vi.fn(),
  listSupplierRecords: vi.fn(),
  updateSupplier: vi.fn(),
  confirmSupplierAssignmentReview: vi.fn(),
  rejectSupplierAssignmentReview: vi.fn(),
  getSeasonalitySummary: vi.fn(),
  getSeasonalProducts: vi.fn(),
  getProductSeasonality: vi.fn(),
  getStaleDemandReview: vi.fn(),
  getManagerApprovedStaleQueue: vi.fn(),
  getRecommendationReviewSummary: vi.fn(),
  saveStaleDemandReviewDecision: vi.fn(),
  getSupplierForecast: vi.fn(),
  refreshOrderProInventory: vi.fn(),
  createDraftPOFromSupplierForecast: vi.fn(),
  isAuthEnabled: vi.fn(),
  createProductSupplier: vi.fn(),
  confirmProductSupplier: vi.fn(),
  rejectProductSupplier: vi.fn(),
  setPreferredProductSupplier: vi.fn(),
  unsetPreferredProductSupplier: vi.fn(),
  listPurchaseOrders: vi.fn(),
  getPurchaseOrder: vi.fn(),
  getPurchaseOrderExternalSendReadiness: vi.fn(),
  getPurchaseOrderPreflight: vi.fn(),
  listRecommendations: vi.fn(),
  getRecommendation: vi.fn(),
  getRecommendationPOReadiness: vi.fn(),
  createReorderRecommendation: vi.fn(),
  createManagerApprovedStaleReviewRecommendation: vi.fn(),
  exportStaleDemandReviewCsv: vi.fn(),
  exportManagerApprovedStaleQueueCsv: vi.fn(),
  exportRecommendationCleanupCandidatesCsv: vi.fn(),
  exportRecommendationReviewSummaryCsv: vi.fn(),
  acceptRecommendation: vi.fn(),
  rejectRecommendation: vi.fn(),
  convertRecommendationToDraftPO: vi.fn(),
  createDraftPurchaseOrderFromProducts: vi.fn(),
  createPurchaseOrder: vi.fn(),
  exportPurchaseOrderHandoffPacket: vi.fn(),
  exportPurchaseOrderCsv: vi.fn(),
  addPurchaseOrderLine: vi.fn(),
  updatePurchaseOrderLine: vi.fn(),
  submitPurchaseOrderForApproval: vi.fn(),
  approvePurchaseOrder: vi.fn(),
  issuePurchaseOrder: vi.fn(),
  receivePurchaseOrder: vi.fn(),
  cancelPurchaseOrder: vi.fn(),
}));

const productDefaults: Product = {
  id: 1,
  name: "Mapped Product",
  supplier: null,
  orderpro_sku: "OP-1",
  supplier_id: 10,
  supplier_name: "Acme Supplies",
  supplier_code: "ACME",
  supplier_sku: "ACME-1",
  current_stock: 12,
  supplier_count: 1,
  preferred_supplier: "Acme Supplies",
  preferred_supplier_id: 10,
  preferred_supplier_sku: "ACME-1",
  supplier_mappings: [],
  mapping_status: "mapped",
};

const supplierMappingDefaults: ProductSupplierMapping = {
  id: 100,
  product_id: 1,
  product_name: "Mapped Product",
  supplier_id: 10,
  supplier_name: "Acme Supplies",
  supplier_sku: "ACME-1",
  supplier_product_name: "Acme Product Pack",
  purchase_price: 9.5,
  currency: "USD",
  minimum_order_quantity: null,
  pack_size: null,
  lead_time_days: null,
  is_preferred: true,
  match_status: "matched",
  match_method: "sku",
  match_confidence: null,
  last_synced_at: null,
};

function mockProduct(overrides: Partial<Product> = {}): Product {
  return {
    ...productDefaults,
    ...overrides,
  };
}

function mockSupplierMapping(
  overrides: Partial<ProductSupplierMapping> = {},
): ProductSupplierMapping {
  return {
    ...supplierMappingDefaults,
    ...overrides,
  };
}

function mockWeakMapping(overrides: Partial<WeakMapping> = {}): WeakMapping {
  return {
    product_id: 2,
    product_name: "Questionable Product",
    reason: "Low confidence",
    mapping_id: 200,
    supplier_id: 20,
    supplier_name: "Maybe Supplier",
    supplier_sku: "MAYBE-2",
    supplier_product_name: "Maybe Product",
    match_status: "review",
    match_method: "fuzzy",
    match_confidence: 0.4,
    ...overrides,
  };
}

function mockForecast(overrides: Partial<ForecastResponse> = {}): ForecastResponse {
  return {
    product_id: 1,
    product_name: "Mapped Product",
    orderpro_sku: "OP-1",
    current_stock: 12,
    inventory_source: "product_record",
    avg_daily_usage: 1.5,
    demand_source: "orderpro_orders",
    demand_lookback_days: 90,
    demand_history_start: "2026-06-01",
    demand_history_end: "2026-06-05",
    observation_days: 5,
    shipped_units_in_window: 10,
    shipped_order_count: 2,
    open_confirmed_units: 0,
    open_packed_units: 0,
    open_backorder_units: 0,
    total_open_demand: 0,
    effective_available_stock: 12,
    net_available_stock: 12,
    projected_lead_time_demand: 6,
    total_required_stock: 6,
    incoming_qty: 0,
    effective_available_stock_for_reorder: 12,
    recommended_qty_before_inbound: 0,
    recommended_qty_after_inbound: 0,
    inbound_adjustment_qty: 0,
    units_sold_in_window: 10,
    eligible_order_count: 2,
    excluded_order_count: 0,
    days_until_stockout: 8,
    supplier_name: "Acme Supplies",
    matched_sku: "ACME-1",
    lead_time_days_used: 4,
    lead_time_source: "product_supplier",
    supplier_context: {
      supplier_id: 10,
      supplier_name: "Acme Supplies",
      supplier_code: "ACME",
      supplier_sku: "ACME-1",
      supplier_product_name: "Acme Product Pack",
      purchase_price: 9.5,
      currency: "USD",
      lead_time_days: 4,
      lead_time_source: "product_supplier",
      minimum_order_quantity: 6,
      moq_source: "product_supplier",
      match_status: "matched",
      match_method: "sku",
      mapping_source: "orderpro_product_supplier",
      has_supplier_mapping: true,
      needs_supplier_mapping: false,
    },
    incoming_stock_context: {
      product_id: 1,
      incoming_qty: 0,
      incoming_qty_local: 0,
      incoming_qty_orderpro: 0,
      incoming_qty_total: 0,
      incoming_qty_by_source: {},
      source_breakdown: {},
      open_po_count: 0,
      open_po_line_count: 0,
      earliest_expected_date: null,
      latest_expected_date: null,
      supplier_ids: [],
      warnings: [],
    },
    forecast_input_context: {
      product_id: 1,
      cost_price: 9.5,
      cost_source: "orderpro_product_cost",
      cost_confidence: "high",
      lead_time_days: 4,
      lead_time_source: "product_record",
      lead_time_confidence: "high",
      min_order_qty: 6,
      moq_source: "product_record",
      pack_size: null,
      pack_size_source: "missing",
      safety_stock: 0,
      safety_stock_source: "product_record",
      blocking_issues: [],
      warning_issues: ["missing_pack_size"],
      readiness_score: 87.5,
    },
    cost_price: 9.5,
    cost_source: "orderpro_product_cost",
    cost_confidence: "high",
    estimated_unit_cost: 9.5,
    estimated_cost_source: "orderpro_product_cost",
    estimated_purchase_value: null,
    moq_source: "product_record",
    pack_size: null,
    pack_size_source: "missing",
    safety_stock_used: 0,
    safety_stock_source: "product_record",
    input_blocking_issues: [],
    input_warning_issues: ["missing_pack_size"],
    forecast_readiness_score: 87.5,
    reorder_point: 6,
    recommended_action: "monitor",
    recommended_qty: 0,
    risk_level: "low",
    explanation: "Current stock is sufficient.",
    seasonality_context: {
      seasonality_tag: "summer",
      current_status: "in_season",
      selected_month_index: 1.8,
      primary_season: "summer",
      peak_months: [6, 7, 8],
      confidence_score: 0.82,
      confidence_label: "high",
      advisory_message: "June is part of this product's elevated demand period.",
    },
    ...overrides,
  };
}

function mockForecastReadinessSummary(
  overrides: Partial<ForecastReadinessSummary> = {},
): ForecastReadinessSummary {
  return {
    product_count: 3,
    products_with_complete_critical_inputs: 1,
    products_missing_supplier: 1,
    products_missing_lead_time: 1,
    products_missing_cost: 1,
    products_missing_moq: 0,
    products_missing_pack_size: 2,
    products_using_fallback_moq: 1,
    products_using_po_derived_cost: 1,
    products_using_orderpro_cost: 1,
    suppliers_missing_lead_time: 1,
    products_blocked_by_missing_supplier: 1,
    products_blocked_by_missing_demand: 0,
    products_complete_before_reconciliation: 1,
    products_complete_after_reconciliation: 2,
    products_missing_demand_history: 0,
    products_missing_seasonality: 2,
    products_with_validated_seasonality: 0,
    products_with_harmful_seasonality: 0,
    ...overrides,
  };
}

function mockForecastInputAudit(overrides: Partial<ForecastInputAudit> = {}): ForecastInputAudit {
  return {
    product_id: 77,
    orderpro_sku: "READY-77",
    product_name: "Ready Product",
    available_inputs: ["supplier_id", "cost_price", "lead_time"],
    missing_inputs: ["pack_size"],
    inputs_currently_used: ["supplier_id", "current_stock"],
    advisory_inputs: [],
    blocking_issues: [],
    warning_issues: ["missing_pack_size", "fallback_moq"],
    forecast_readiness_score: 87.5,
    cost_price: 6.5,
    cost_source: "orderpro_purchase_order_line",
    cost_confidence: "medium",
    lead_time_days: 5,
    lead_time_source: "supplier_record",
    lead_time_confidence: "medium",
    min_order_qty: 1,
    moq_source: "business_default",
    pack_size: null,
    pack_size_source: "missing",
    safety_stock: 0,
    safety_stock_source: "product_record",
    seasonality_activation_recommendation: "safe_for_advisory_only",
    seasonality_readiness_status: null,
    forecast_recommended_qty: 0,
    ...overrides,
  };
}

function mockForecastReconciliationSummary(
  overrides: Partial<ForecastReconciliationSummary> = {},
): ForecastReconciliationSummary {
  return {
    total_products: 3,
    ready: 1,
    partially_ready: 1,
    blocked: 1,
    monitor_only: 0,
    missing_supplier: 1,
    missing_lead_time: 1,
    missing_cost: 1,
    missing_pack_size: 1,
    missing_demand_history: 1,
    missing_stock: 0,
    readiness_percentage: 66.67,
    ...overrides,
  };
}

function mockForecastReconciliationProduct(
  overrides: Partial<ForecastReconciliationProduct> = {},
): ForecastReconciliationProduct {
  return {
    product_id: 77,
    sku: "READY-77",
    orderpro_sku: "READY-77",
    product_name: "Ready Product",
    description: "Operationally ready product",
    barcode: "1234567890",
    supplier_id: 10,
    supplier_code: "ACME",
    supplier_name: "Acme Supplies",
    supplier_source: "manual_supplier_cleanup",
    current_stock: 12,
    stock_source: "product_current_stock_cache",
    demand_history_available: true,
    demand_source: "orderpro_orders",
    open_customer_demand: 3,
    lead_time_days: 5,
    lead_time_source: "supplier_record",
    cost_price: 6.5,
    cost_source: "orderpro_product_cost",
    pack_size: 2,
    pack_size_source: "forecast_input_profile",
    min_order_qty: 1,
    moq_source: "business_default",
    seasonality_status: "year_round",
    readiness_score: 100,
    readiness_status: "ready",
    missing_inputs: [],
    warnings: [],
    blocking_issues: [],
    recommendation_status: "monitor",
    recommended_quantity: 0,
    explanation: "Ready for normal forecasting.",
    sources: {
      supplier: "manual_supplier_cleanup",
      lead_time: "supplier_record",
      stock: "product_current_stock_cache",
      demand: "orderpro_orders",
      cost: "orderpro_product_cost",
      pack_size: "forecast_input_profile",
      seasonality: "year_round",
    },
    inputs: {
      supplier: {
        value: "Acme Supplies",
        supplier_id: 10,
        source: "manual_supplier_cleanup",
        is_missing: false,
        is_fallback: false,
        blocks_forecast: false,
      },
    },
    ...overrides,
  };
}

function mockDemandHistorySummary(
  overrides: Partial<DemandHistorySummary> = {},
): DemandHistorySummary {
  return {
    total_products: 3,
    products_with_demand_history: 2,
    products_without_demand_history: 1,
    products_with_recent_demand: 1,
    products_with_stale_demand: 1,
    total_demand_rows: 24,
    earliest_demand_date: "2022-01-01",
    latest_demand_date: "2025-12-03",
    coverage_percentage: 66.67,
    products_blocked_by_missing_demand_history: 1,
    selected_date: "2026-06-18",
    ...overrides,
  };
}

function mockDemandHistoryProduct(
  overrides: Partial<DemandHistoryProduct> = {},
): DemandHistoryProduct {
  return {
    product_id: 7832,
    sku: "DEMAND-7832",
    orderpro_sku: "DEMAND-7832",
    barcode: "1234567890",
    description: "Demand-covered product",
    product_name: "Demand Covered Product",
    supplier_id: 34,
    supplier_code: "SUP34",
    supplier_name: "Demand Supplier",
    current_stock: 8,
    has_demand_history: true,
    demand_row_count: 12,
    earliest_demand_date: "2022-01-01",
    latest_demand_date: "2025-12-03",
    months_covered: 18,
    total_units: 144,
    units_last_30_days: 6,
    units_last_90_days: 18,
    average_monthly_units: 8,
    return_units: 2,
    stale_demand: false,
    gap_warnings: ["Missing recent month"],
    readiness_status: "ready",
    readiness_score: 90,
    readiness_missing_inputs: [],
    demand_source: "usage_history",
    monthly_buckets: [
      { month: "2025-12", net_units: 12, return_units: 1 },
      { month: "2025-11", net_units: 8, return_units: 0 },
    ],
    source_systems: ["demand_history_import"],
    readiness_impact: "Demand history is present.",
    current_forecast_demand_source: "usage_history",
    ...overrides,
  };
}

function mockSupplierAssignmentSummary(
  overrides: Partial<SupplierAssignmentReviewSummary> = {},
): SupplierAssignmentReviewSummary {
  return {
    total_orderpro_products: 3,
    missing_supplier_products: 2,
    missing_supplier_products_with_stock: 1,
    missing_supplier_products_with_demand_history: 1,
    missing_supplier_products_with_open_customer_demand: 1,
    missing_supplier_products_with_seasonality_profile: 0,
    missing_supplier_products_with_po_supplier_evidence: 1,
    missing_supplier_products_with_no_evidence: 1,
    suggested_supplier_count_by_confidence: { high: 1, none: 1 },
    suggestion_count_by_source: { orderpro_purchase_orders_repeated: 1, none: 1 },
    review_status_counts: { suggested: 1, no_evidence: 1 },
    no_suggestion_count: 1,
    top_categories_affected: { Tack: 1 },
    top_brands_affected: { Stable: 1 },
    ...overrides,
  };
}

function mockSupplierAssignmentItem(
  overrides: Partial<SupplierAssignmentReviewItem> = {},
): SupplierAssignmentReviewItem {
  return {
    product_id: 8182,
    orderpro_id: "8182",
    orderpro_sku: "MISS-SUP",
    name: "Missing Supplier Product",
    barcode: "123",
    brand: "Stable",
    category: "Tack",
    current_stock: 4,
    demand_history_available: true,
    open_customer_demand: 6,
    seasonality_tag: "summer",
    cost_source: "orderpro_product_cost",
    lead_time_status: "missing",
    suggested_supplier_id: 34,
    suggested_supplier_name: "Suggested Supplier",
    suggestion_source: "orderpro_purchase_orders_repeated",
    confidence_label: "high",
    confidence_score: 0.9,
    evidence_summary: { message: "Repeated OrderPro PO evidence" },
    evidence_date: "2026-06-10T10:00:00",
    warnings: [],
    status: "suggested",
    review_id: 22,
    reviewed_supplier_id: null,
    reviewed_by: null,
    reviewed_at: null,
    ...overrides,
  };
}

function mockSupplierOption(overrides: Partial<SupplierOption> = {}): SupplierOption {
  return {
    id: 34,
    name: "Suggested Supplier",
    orderpro_id: "34",
    orderpro_code: "SUG",
    is_active: true,
    lead_time_days: 7,
    ...overrides,
  };
}

function mockSupplierRecord(overrides: Partial<SupplierRecord> = {}): SupplierRecord {
  return {
    ...mockSupplierOption({
      id: 18,
      name: "ED&F Man",
      orderpro_id: "18",
      orderpro_code: "ED&FMAN",
      lead_time_days: null,
    }),
    source_system: "orderpro",
    local_profile_override: false,
    last_synced_at: "2026-08-21T09:00:00",
    email: "sales@edfman.test",
    phone: null,
    website: null,
    contact_method: null,
    payment_terms: null,
    lead_time_raw: null,
    lead_time_min_days: null,
    lead_time_max_days: null,
    notes: null,
    active_skus: 2,
    lead_time_needs_review: true,
    product_count: 2,
    active_product_count: 2,
    writes_to_orderpro: false,
    ...overrides,
  };
}

function mockSeasonalitySummary(
  overrides: Partial<SeasonalitySummary> = {},
): SeasonalitySummary {
  return {
    classification_counts: {
      insufficient_data: 1170,
      year_round: 179,
      summer: 33,
      autumn: 44,
      spring: 20,
      winter: 28,
      multi_peak: 10,
    },
    confidence_counts: {
      high: 42,
      medium: 83,
      low: 189,
      insufficient: 1170,
    },
    current_season_counts: {
      insufficient_data: 1170,
      year_round: 179,
      approaching_season: 38,
      in_season: 24,
      off_season: 73,
    },
    profile_count: 1484,
    product_count: 1484,
    missing_profile_count: 0,
    selected_month: 6,
    include_legacy: false,
    ...overrides,
  };
}

function mockSeasonalProduct(overrides: Partial<SeasonalProduct> = {}): SeasonalProduct {
  return {
    product_id: 7832,
    orderpro_sku: "SUMMER-7832",
    name: "Seasonal Fly Sheet",
    supplier_id: 34,
    supplier_name: "Seasonal Supplier",
    current_stock: 0,
    seasonality_tag: "summer",
    current_seasonality_status: "in_season",
    selected_month: 6,
    selected_month_units: 44,
    selected_month_index: 1.8,
    peak_months: [6, 7, 8],
    primary_season: "summer",
    seasonality_strength: 0.8,
    confidence_score: 0.86,
    confidence_label: "high",
    history_start: "2022-01-01",
    history_end: "2025-12-03",
    years_covered: 4,
    ...overrides,
  };
}

function mockProductSeasonalityDetail(
  overrides: Partial<ProductSeasonalityDetail> = {},
): ProductSeasonalityDetail {
  return {
    product_id: 7832,
    orderpro_sku: "SUMMER-7832",
    name: "Seasonal Fly Sheet",
    history_start: "2022-01-01",
    history_end: "2025-12-03",
    history_months: 48,
    active_months: 28,
    years_covered: 4,
    total_units: 320,
    average_monthly_units: 26.67,
    monthly_units: { "6": 44, "7": 48, "8": 45 },
    monthly_indices: { "6": 1.8, "7": 1.95, "8": 1.82 },
    peak_months: [6, 7, 8],
    low_months: [1, 2],
    primary_season: "summer",
    seasonality_tag: "summer",
    seasonality_strength: 0.8,
    confidence_score: 0.86,
    confidence_label: "high",
    coefficient_of_variation: 0.42,
    calculation_version: "seasonality-v1",
    calculated_at: "2026-06-10T10:00:00",
    current_interpretation: {
      current_status: "in_season",
      selected_month: 6,
      selected_month_units: 44,
      selected_month_index: 1.8,
      advisory_message: "June is part of this product's elevated demand period.",
    },
    direct_history_row_count: 0,
    linked_history_row_count: 24,
    contributing_historical_product_ids: [101, 102],
    reconciliation_methods: ["barcode_exact"],
    ...overrides,
  };
}

function mockPurchaseOrder(overrides: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: 500,
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    status: "draft",
    created_at: "2026-05-28T10:00:00",
    updated_at: "2026-05-28T10:00:00",
    approved_at: null,
    issued_at: null,
    received_at: null,
    cancelled_at: null,
    notes: "Draft PO",
    total_amount: 19,
    currency: "USD",
    created_by: "tester",
    approved_by: null,
    lines: [
      {
        id: 700,
        purchase_order_id: 500,
        product_id: 1,
        product_name: null,
        product_supplier_id: null,
        supplier_sku: "ACME-1",
        supplier_product_name: "Acme Product Pack",
        quantity: 2,
        unit_cost: 9.5,
        currency: "USD",
        line_total: 19,
        minimum_order_quantity: 1,
        pack_size: 1,
        lead_time_days: 4,
        notes: "Line notes",
      },
    ],
    ...overrides,
  };
}

function mockPurchaseOrderPreflight(
  overrides: Partial<PurchaseOrderPreflight> = {},
): PurchaseOrderPreflight {
  return {
    purchase_order_id: 500,
    status: "draft",
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    can_submit: true,
    can_approve: false,
    can_issue_if_applicable: false,
    overall_status: "needs_review",
    blockers: [],
    warnings: ["Missing pack size; review before ordering."],
    line_checks: [
      {
        line_id: 700,
        product_id: 1,
        product_name: "Mapped Product",
        supplier_id: 10,
        supplier_name: "Acme Supplies",
        quantity: 2,
        unit_cost: 9.5,
        estimated_line_total: 19,
        product_supplier_id: null,
        source_recommendation_id: null,
        is_inventory_product: true,
        canonical_supplier_matches_po_supplier: true,
        quantity_valid: true,
        cost_present: true,
        supplier_snapshot_present: true,
        blockers: [],
        warnings: ["Missing pack size; review before ordering."],
      },
    ],
    summary_counts: {
      line_count: 1,
      blocker_count: 0,
      warning_count: 1,
      lines_with_blockers: 0,
      lines_with_warnings: 1,
    },
    ...overrides,
  };
}

function mockPurchaseOrderExternalSendReadiness(
  overrides: Partial<PurchaseOrderExternalSendReadiness> = {},
): PurchaseOrderExternalSendReadiness {
  return {
    purchase_order_id: 500,
    status: "draft",
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    can_send_externally: false,
    external_send_supported: false,
    external_send_system: "OrderPro",
    blockers: ["External OrderPro sending is not implemented yet."],
    warnings: ["Future external sending should require the PO to be locally issued first."],
    required_local_status: "issued",
    preflight_summary: {
      overall_status: "needs_review",
      can_submit: true,
      can_approve: false,
      can_issue_if_applicable: false,
      blocker_count: 0,
      warning_count: 1,
      line_count: 1,
      blockers: [],
      warnings: ["Missing pack size; review before ordering."],
    },
    message: "This purchase order is local-only. External OrderPro sending is not implemented yet.",
    ...overrides,
  };
}

function mockRecommendation(overrides: Partial<PurchaseRecommendation> = {}): PurchaseRecommendation {
  return {
    id: 900,
    product_id: 1,
    product_name: "Mapped Product",
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    product_supplier_id: 100,
    converted_purchase_order_id: null,
    recommendation_type: "reorder",
    status: "pending_review",
    recommended_quantity: 6,
    recommended_supplier_name: "Acme Supplies",
    recommended_supplier_sku: "ACME-1",
    estimated_unit_cost: 9.5,
    estimated_total_cost: 57,
    currency: "USD",
    reason: "Stock is below reorder point.",
    confidence: null,
    input_snapshot: {
      effective_forecast_inputs: {
        cost_price: 9.5,
        cost_source: "orderpro_product_cost",
        min_order_qty: 2,
        moq_source: "product_record",
        pack_size: null,
        pack_size_source: "missing",
        pack_size_required: false,
        cost_required: false,
      },
    },
    forecast_snapshot: {
      recommended_action: "order_now",
      risk_level: "high",
      current_stock: 1,
      eligible_order_count: 4,
      units_sold_in_window: 18,
      legacy_demand_quantity_mode: "net_qty",
      demand_policy_status: "recent_or_current",
      demand_history_end: "2026-07-01",
      stale_demand_only: false,
      legacy_demand_negative_or_return_rows: 1,
      avg_daily_usage: 0.6,
      lead_time_days_used: 4,
      days_until_stockout: 1.67,
      reorder_point: 12,
      input_blocking_issues: [],
      input_warning_issues: ["missing_pack_size"],
      purchase_readiness_status: "order_ready",
      not_ready_for_po: false,
      suggested_cleanup_action: "none",
      quantity_review_note: "Ready for PO using current MOQ and pack-size inputs.",
      quantity_was_rounded_to_pack_size: false,
      pack_size_required: false,
      cost_required: false,
      stale_demand_policy: "recent_or_not_legacy",
      stale_demand_recommendations_allowed: false,
      explanation: "Stock is below reorder point.",
    },
    supplier_context_snapshot: {
      supplier_name: "Acme Supplies",
      supplier_sku: "ACME-1",
      supplier_product_name: "Acme Product Pack",
      mapping_source: "product_supplier",
      lead_time_days: 4,
      minimum_order_quantity: 6,
      purchase_price: 9.5,
    },
    model_name: null,
    prompt_version: null,
    generated_by: "system",
    reviewed_by: null,
    reviewed_at: null,
    rejected_reason: null,
    created_at: "2026-05-28T10:00:00",
    updated_at: "2026-05-28T10:00:00",
    ...overrides,
  };
}

function mockRecommendationPOReadiness(
  overrides: Partial<RecommendationPOReadiness> = {},
): RecommendationPOReadiness {
  return {
    recommendation_id: 900,
    product_id: 1,
    product_name: "Mapped Product",
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    recommendation_status: "accepted",
    recommendation_type: "reorder",
    recommended_quantity: 6,
    estimated_unit_cost: 9.5,
    estimated_total_cost: 57,
    can_create_draft_po: true,
    blockers: [],
    warnings: ["Missing pack size; no order multiple is applied unless reviewed"],
    required_manager_decision: null,
    po_supplier_source: "products.supplier_id",
    canonical_supplier_check_result: "ok",
    product_supplier_id: null,
    recommendation_supplier_id: 10,
    forecast_recommended_action: "reorder",
    stale_demand_only: false,
    review_decision: null,
    purchase_readiness_status: "order_ready",
    ...overrides,
  };
}

function mockStaleDemandReview(
  overrides: Partial<StaleDemandReviewResponse> = {},
): StaleDemandReviewResponse {
  return {
    summary: {
      products_evaluated: 0,
      total_candidates: 0,
      suggested_action_counts: {},
      skipped_counts: {},
      limit: 500,
    },
    items: [],
    ...overrides,
  };
}

function mockStaleDemandReviewWithCandidate(): StaleDemandReviewResponse {
  return mockStaleDemandReview({
    summary: {
      products_evaluated: 1,
      total_candidates: 1,
      suggested_action_counts: { manual_review: 1 },
      skipped_counts: {},
      limit: 500,
    },
    items: [
      {
        product_id: 3020,
        product_name: "Stale Product",
        orderpro_sku: "STALE-3020",
        supplier_id: 10,
        supplier_name: "Acme Supplies",
        last_demand_date: "2025-01-01",
        days_since_last_demand: 560,
        demand_rows: 4,
        monthly_average_demand: 2.5,
        current_stock: 0,
        lead_time_days: 4,
        advisory_recommended_quantity: 6,
        estimated_unit_cost: 9.5,
        estimated_total_cost: 57,
        blockers: [],
        warnings: ["Stale demand only; last demand is older than 180 days"],
        purchase_readiness_issues: ["Stale-only demand requires manual review"],
        suggested_action: "manual_review",
        stale_demand_policy: "manual_review_required",
        review_decision: null,
        reviewed_by: null,
        review_notes: null,
        reviewed_at: null,
        decision_status: "unreviewed",
        recommendation_status: "needs_review",
        purchase_readiness_status: "blocked",
      },
    ],
  });
}

function mockManagerApprovedStaleQueue(
  overrides: Partial<ManagerApprovedStaleQueueResponse> = {},
): ManagerApprovedStaleQueueResponse {
  return {
    summary: {
      decisions_evaluated: 1,
      total_candidates: 1,
      safety_status_counts: { ready_for_manual_recommendation: 1 },
      suggested_next_action_counts: { create_review_recommendation: 1 },
      limit: 500,
    },
    items: [
      {
        product_id: 3020,
        product_name: "Stale Product",
        orderpro_sku: "STALE-3020",
        supplier_id: 10,
        supplier_name: "Acme Supplies",
        lead_time_days: 4,
        current_stock: 0,
        last_demand_date: "2025-01-01",
        days_since_last_demand: 560,
        advisory_recommended_quantity: 6,
        estimated_unit_cost: 9.5,
        estimated_total_cost: 57,
        reviewed_by: "Maged",
        review_notes: "Approved for one-time reorder.",
        reviewed_at: "2026-07-14T10:00:00",
        review_decision: "manager_approved_one_time",
        safety_status: "ready_for_manual_recommendation",
        safety_blockers: [],
        warnings: [],
        suggested_next_action: "create_review_recommendation",
        recommendation_status: "needs_review",
        purchase_readiness_status: "partially_ready",
      },
    ],
    ...overrides,
  };
}

function mockRecommendationReviewSummary(
  overrides: Partial<RecommendationReviewSummaryResponse["summary"]> = {},
): RecommendationReviewSummaryResponse {
  return {
    summary: {
      total_existing_recommendations: 3,
      pending_review_recommendations: 1,
      accepted_recommendations: 1,
      rejected_recommendations: 1,
      recommendation_status_counts: { pending_review: 1, accepted: 1, rejected: 1 },
      stale_demand_candidates: 2,
      stale_demand_decisions_by_type: { manager_approved_one_time: 1 },
      manager_approved_stale_queue_count: 1,
      manager_approved_stale_queue_by_safety_status: { ready_for_manual_recommendation: 1 },
      cleanup_candidates_count: 1,
      cleanup_candidates_by_issue: { stale_demand_review_required: 1 },
      recommendations_ready_for_manual_review: 1,
      recommendations_blocked_from_po_conversion: 1,
      limit: 500,
      ...overrides,
    },
  };
}

function mockLLMExplanation(
  overrides: Partial<RecommendationLLMExplanation> = {},
): RecommendationLLMExplanation {
  return {
    suggested_action: "reorder",
    summary: "Review reorder recommendation for Mapped Product.",
    explanation: "The recommendation suggests 6 units from Acme Supplies.",
    risk_flags: ["Forecast risk level is high."],
    missing_data_warnings: [],
    confidence: 0.8,
    structured_data_citations: [
      "recommendation.recommended_qty",
      "recommendation.forecast_snapshot",
    ],
    model_name: "mock",
    prompt_version: "mock-v1",
    ...overrides,
  };
}

function mockDraftFromProductsResponse(overrides: Partial<PurchaseOrder> = {}) {
  const purchaseOrder = mockPurchaseOrder(overrides);
  return {
    purchase_order: purchaseOrder,
    created_purchase_orders: [purchaseOrder],
    summary: {
      created_po_count: 1,
      created_line_count: 1,
      skipped_products: [],
      grouped_by_supplier: { "10": 1 },
    },
  };
}

function mockSupplierForecast(overrides: Partial<SupplierForecastResponse> = {}): SupplierForecastResponse {
  return {
    supplier_id: 10,
    supplier_name: "Acme Supplies",
    supplier_code: "ACME",
    product_count: 1,
    forecasts: [mockForecast({ recommended_action: "reorder", recommended_qty: 6 })],
    products_needing_reorder: [1],
    products_missing_data: [],
    low_stock_products: [1],
    out_of_stock_products: [],
    incoming_covered_products: [],
    high_risk_products: [],
    stock_status: "low_stock",
    inventory_last_synced_at: "2026-08-24T08:00:00",
    total_current_stock: 5,
    total_incoming_quantity: 0,
    total_recommended_quantity: 6,
    total_estimated_cost: 57,
    ...overrides,
  };
}

function mockCleanupSummary(overrides: Partial<ManualSupplierCleanupSummary> = {}): ManualSupplierCleanupSummary {
  return {
    total_products: 3,
    products_with_supplier: 1,
    products_missing_supplier: 2,
    priority_missing_supplier_products: 1,
    confirmed_manual_assignments: 0,
    deferred_reviews: 0,
    rejected_reviews: 0,
    needs_information_reviews: 0,
    completion_percentage: 33.33,
    ...overrides,
  };
}

function mockCleanupCandidate(
  overrides: Partial<ManualSupplierCleanupCandidate> = {},
): ManualSupplierCleanupCandidate {
  return {
    product_id: 71,
    orderpro_id: "op-71",
    orderpro_sku: "CLEAN-71",
    product_name: "Cleanup Product",
    barcode: "123456",
    brand: "Stable",
    category: "Grooming",
    description: "Needs supplier review",
    current_stock: 4,
    demand_history_available: true,
    open_customer_demand: 6,
    seasonality_tag: "summer",
    cost_price: 12.5,
    cost_source: "product",
    lead_time_status: "available",
    forecast_readiness_score: 80,
    blocking_issues: ["missing_supplier"],
    warning_issues: [],
    existing_suggested_supplier_id: 10,
    existing_suggested_supplier_name: "Acme Supplies",
    existing_suggestion_source: "orderpro_purchase_order_line",
    existing_confidence_label: "medium",
    evidence_summary: { message: "Recent PO evidence" },
    review_status: "suggested",
    priority_score: 105,
    priority_reason: "open customer demand; stock on hand",
    suggested_action: "confirm_existing_suggestion",
    review: null,
    ...overrides,
  };
}

function mockCleanupSupplier(
  overrides: Partial<ManualSupplierCleanupSupplier> = {},
): ManualSupplierCleanupSupplier {
  return {
    id: 10,
    name: "Acme Supplies",
    orderpro_id: "sup-10",
    orderpro_code: "ACME",
    is_active: true,
    lead_time_days: 7,
    assigned_product_count: 12,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getStoredAccessToken).mockReturnValue("test-token");
  vi.mocked(isAuthEnabled).mockReturnValue(true);
  vi.mocked(getCurrentAdmin).mockResolvedValue({ email: "admin@example.com", role: "admin" });
  vi.mocked(loginAdmin).mockResolvedValue({
    access_token: "new-token",
    token_type: "bearer",
    expires_in: 3600,
  });
  vi.mocked(fetchProducts).mockResolvedValue([]);
  vi.mocked(fetchUnmappedProducts).mockResolvedValue([]);
  vi.mocked(fetchWeakMappings).mockResolvedValue([]);
  vi.mocked(fetchProductSuppliers).mockResolvedValue([]);
  vi.mocked(fetchProductForecast).mockResolvedValue(mockForecast());
  vi.mocked(getForecastReadinessSummary).mockResolvedValue(mockForecastReadinessSummary());
  vi.mocked(getForecastReadinessRows).mockResolvedValue([mockForecastInputAudit()]);
  vi.mocked(getForecastReconciliationSummary).mockResolvedValue(mockForecastReconciliationSummary());
  vi.mocked(getForecastReconciliationProducts).mockResolvedValue({
    items: [
      mockForecastReconciliationProduct(),
      mockForecastReconciliationProduct({
        product_id: 88,
        sku: "MISSING-SUP",
        orderpro_sku: "MISSING-SUP",
        product_name: "Missing Supplier Product",
        supplier_id: null,
        supplier_code: null,
        supplier_name: null,
        supplier_source: "missing",
        readiness_score: 66.67,
        readiness_status: "blocked",
        missing_inputs: ["supplier_id"],
        blocking_issues: ["missing_supplier"],
        explanation: "Supplier assignment is blocking forecast readiness.",
      }),
      mockForecastReconciliationProduct({
        product_id: 89,
        sku: "NO-HISTORY",
        orderpro_sku: "NO-HISTORY",
        product_name: "Monitor Only Product",
        demand_history_available: false,
        demand_source: "none",
        open_customer_demand: 0,
        readiness_score: 77.78,
        readiness_status: "monitor_only",
        missing_inputs: ["demand_history"],
        warnings: ["missing_demand_history"],
        explanation: "No demand history is available yet.",
      }),
    ],
    page: 1,
    page_size: 25,
    total: 3,
    total_pages: 1,
    summary: mockForecastReconciliationSummary(),
  });
  vi.mocked(getForecastReconciliationProduct).mockResolvedValue(mockForecastReconciliationProduct());
  vi.mocked(exportForecastReconciliationCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "forecast_readiness.csv",
  });
  vi.mocked(getDemandHistorySummary).mockResolvedValue(mockDemandHistorySummary());
  vi.mocked(getDemandHistoryProducts).mockResolvedValue({
    items: [
      mockDemandHistoryProduct(),
      mockDemandHistoryProduct({
        product_id: 7900,
        sku: "MISSING-HISTORY",
        orderpro_sku: "MISSING-HISTORY",
        product_name: "Missing History Product",
        has_demand_history: false,
        demand_row_count: 0,
        earliest_demand_date: null,
        latest_demand_date: null,
        months_covered: 0,
        total_units: 0,
        units_last_30_days: 0,
        units_last_90_days: 0,
        average_monthly_units: 0,
        return_units: 0,
        stale_demand: false,
        gap_warnings: ["No local demand history"],
        readiness_status: "blocked",
        readiness_score: 55,
        readiness_missing_inputs: ["demand_history"],
        demand_source: "none",
      }),
    ],
    page: 1,
    page_size: 25,
    total: 2,
    total_pages: 1,
  });
  vi.mocked(getDemandHistoryProduct).mockResolvedValue(mockDemandHistoryProduct());
  vi.mocked(exportDemandHistoryCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "demand_coverage.csv",
  });
  vi.mocked(getSupplierAssignmentReviewSummary).mockResolvedValue(mockSupplierAssignmentSummary());
  vi.mocked(getSupplierAssignmentReviewItems).mockResolvedValue([]);
  vi.mocked(getManualSupplierCleanupSummary).mockResolvedValue(mockCleanupSummary());
  vi.mocked(getManualSupplierCleanupCandidates).mockResolvedValue({
    items: [mockCleanupCandidate()],
    page: 1,
    page_size: 25,
    total: 1,
    total_pages: 1,
    summary: {
      total_missing_supplier: 1,
      priority_candidates: 1,
      with_open_demand: 1,
      with_stock: 1,
      with_demand_history: 1,
      with_cost: 1,
    },
  });
  vi.mocked(getManualSupplierCleanupCandidate).mockResolvedValue(mockCleanupCandidate());
  vi.mocked(searchManualSupplierCleanupSuppliers).mockResolvedValue({
    items: [mockCleanupSupplier()],
    page: 1,
    page_size: 25,
    total: 1,
    total_pages: 1,
  });
  vi.mocked(assignManualSupplierCleanupCandidate).mockResolvedValue({});
  vi.mocked(reviewManualSupplierCleanupCandidate).mockResolvedValue({});
  vi.mocked(listSuppliers).mockResolvedValue([mockSupplierOption()]);
  vi.mocked(listSupplierRecords).mockResolvedValue([mockSupplierRecord()]);
  vi.mocked(updateSupplier).mockImplementation(async (_supplierId, payload) =>
    mockSupplierRecord({
      ...payload,
      local_profile_override: true,
      lead_time_raw: payload.lead_time_days ? `${payload.lead_time_days} days` : null,
      lead_time_needs_review: !payload.lead_time_days,
    }),
  );
  vi.mocked(confirmSupplierAssignmentReview).mockResolvedValue({});
  vi.mocked(rejectSupplierAssignmentReview).mockResolvedValue({});
  vi.mocked(getSeasonalitySummary).mockResolvedValue(mockSeasonalitySummary());
  vi.mocked(getSeasonalProducts).mockResolvedValue([]);
  vi.mocked(getProductSeasonality).mockResolvedValue(mockProductSeasonalityDetail());
  vi.mocked(getRecommendationReviewSummary).mockResolvedValue(mockRecommendationReviewSummary());
  vi.mocked(getStaleDemandReview).mockResolvedValue(mockStaleDemandReview());
  vi.mocked(getManagerApprovedStaleQueue).mockResolvedValue(
    mockManagerApprovedStaleQueue({
      summary: {
        decisions_evaluated: 0,
        total_candidates: 0,
        safety_status_counts: {},
        suggested_next_action_counts: {},
        limit: 500,
      },
      items: [],
    }),
  );
  vi.mocked(saveStaleDemandReviewDecision).mockResolvedValue({
    id: 1,
    product_id: 3020,
    product_name: "Stale Product",
    orderpro_sku: "STALE-3020",
    recommendation_id: null,
    decision: "manager_approved_one_time",
    reviewed_by: "Maged",
    notes: "Approved for one-time reorder.",
    reviewed_at: "2026-07-14T10:00:00",
    created_at: "2026-07-14T10:00:00",
    updated_at: "2026-07-14T10:00:00",
  });
  vi.mocked(getSupplierForecast).mockResolvedValue(mockSupplierForecast());
  vi.mocked(refreshOrderProInventory).mockResolvedValue({
    source_system: "orderpro",
    records_received: 2,
    records_upserted: 2,
    records_skipped: 0,
    message: "OrderPro stock refresh completed. Purchasing AI was updated; OrderPro was not modified.",
    sync_completed_at: "2026-08-24T08:00:00",
    complete_snapshot: true,
    warehouses_created: 0,
    warehouses_updated: 0,
    inventory_positions_created: 0,
    inventory_positions_updated: 2,
    inventory_positions_zeroed: 0,
    products_current_stock_updated: 2,
    products_current_stock_zeroed: 0,
    rows_missing_product_match: 0,
    rows_missing_warehouse_id: 0,
    unmatched_rows_sample: [],
    warnings: [],
  });
  vi.mocked(generateRecommendationLLMExplanation).mockResolvedValue(mockLLMExplanation());
  vi.mocked(createProductSupplier).mockResolvedValue(mockSupplierMapping());
  vi.mocked(confirmProductSupplier).mockResolvedValue(mockSupplierMapping({ match_status: "confirmed" }));
  vi.mocked(rejectProductSupplier).mockResolvedValue(mockSupplierMapping({ match_status: "rejected" }));
  vi.mocked(setPreferredProductSupplier).mockResolvedValue(mockSupplierMapping({ is_preferred: true }));
  vi.mocked(unsetPreferredProductSupplier).mockResolvedValue(mockSupplierMapping({ is_preferred: false }));
  vi.mocked(listPurchaseOrders).mockResolvedValue([]);
  vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(getPurchaseOrderExternalSendReadiness).mockResolvedValue(
    mockPurchaseOrderExternalSendReadiness(),
  );
  vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(mockPurchaseOrderPreflight());
  vi.mocked(listRecommendations).mockResolvedValue([]);
  vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());
  vi.mocked(getRecommendationPOReadiness).mockResolvedValue(mockRecommendationPOReadiness());
  vi.mocked(createReorderRecommendation).mockResolvedValue(mockRecommendation());
  vi.mocked(createManagerApprovedStaleReviewRecommendation).mockResolvedValue(mockRecommendation());
  vi.mocked(exportStaleDemandReviewCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "stale_demand_review.csv",
  });
  vi.mocked(exportManagerApprovedStaleQueueCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "manager_approved_stale_queue.csv",
  });
  vi.mocked(exportRecommendationReviewSummaryCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "recommendation_review_summary.csv",
  });
  vi.mocked(exportRecommendationCleanupCandidatesCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "recommendation_cleanup_candidates.csv",
  });
  vi.mocked(acceptRecommendation).mockResolvedValue(mockRecommendation({ status: "accepted" }));
  vi.mocked(rejectRecommendation).mockResolvedValue(
    mockRecommendation({ status: "rejected", rejected_reason: "Too early." }),
  );
  vi.mocked(convertRecommendationToDraftPO).mockResolvedValue({
    recommendation: mockRecommendation({ status: "converted_to_po", converted_purchase_order_id: 500 }),
    purchase_order: mockPurchaseOrder({ id: 500, status: "draft" }),
  });
  vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue(
    mockDraftFromProductsResponse({ status: "draft" }),
  );
  vi.mocked(createDraftPOFromSupplierForecast).mockResolvedValue(
    mockDraftFromProductsResponse({ status: "draft" }),
  );
  vi.mocked(createPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(exportPurchaseOrderCsv).mockResolvedValue({
    blob: new Blob(["csv"], { type: "text/csv" }),
    filename: "PO-500.csv",
  });
  vi.mocked(exportPurchaseOrderHandoffPacket).mockResolvedValue({
    blob: new Blob(["zip"], { type: "application/zip" }),
    filename: "purchase-order-po-500-handoff.zip",
  });
  vi.mocked(addPurchaseOrderLine).mockResolvedValue(mockPurchaseOrder());
  vi.mocked(submitPurchaseOrderForApproval).mockResolvedValue(
    mockPurchaseOrder({ status: "pending_approval" }),
  );
  vi.mocked(approvePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({
      status: "approved",
      approved_at: "2026-05-28T11:00:00",
      approved_by: "manager",
    }),
  );
  vi.mocked(issuePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "issued", issued_at: "2026-05-28T12:00:00" }),
  );
  vi.mocked(receivePurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "received", received_at: "2026-05-28T13:00:00" }),
  );
  vi.mocked(cancelPurchaseOrder).mockResolvedValue(
    mockPurchaseOrder({ status: "cancelled", cancelled_at: "2026-05-28T11:00:00" }),
  );
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("App mapping review workflow", () => {
  it("login screen appears when unauthenticated and hides business data", async () => {
    vi.mocked(getStoredAccessToken).mockReturnValue(null);

    render(<App />);

    expect(screen.getByLabelText("Admin login")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Products" })).not.toBeInTheDocument();
    expect(fetchProducts).not.toHaveBeenCalled();
  });

  it("valid login shows the protected application shell", async () => {
    vi.mocked(getStoredAccessToken).mockReturnValue(null);

    render(<App />);
    await userEvent.type(screen.getByLabelText("Email"), "admin@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "test-admin-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(loginAdmin).toHaveBeenCalledWith({
      email: "admin@example.com",
      password: "test-admin-password",
    });
    expect(await screen.findByRole("button", { name: "Products" })).toBeInTheDocument();
  });

  it("invalid login shows a generic error", async () => {
    vi.mocked(getStoredAccessToken).mockReturnValue(null);
    vi.mocked(loginAdmin).mockRejectedValue(new Error("Invalid email or password."));

    render(<App />);
    await userEvent.type(screen.getByLabelText("Email"), "wrong@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "bad-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
    expect(screen.queryByText("bad-password")).not.toBeInTheDocument();
  });

  it("logout clears authentication and returns to login", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Products" });

    await userEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(clearStoredAccessToken).toHaveBeenCalled();
    expect(screen.getByLabelText("Admin login")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Products" })).not.toBeInTheDocument();
  });

  it("401 handler clears authentication and returns to login", async () => {
    render(<App />);
    await screen.findByRole("button", { name: "Products" });
    const handler = vi.mocked(setUnauthorizedHandler).mock.calls.find(
      ([candidate]) => typeof candidate === "function",
    )?.[0] as (() => void) | undefined;

    expect(handler).toBeDefined();
    await act(async () => {
      handler?.();
    });

    expect(screen.getByLabelText("Admin login")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Products" })).not.toBeInTheDocument();
  });

  it("skips login screen and renders the app when authentication is disabled", async () => {
    vi.mocked(isAuthEnabled).mockReturnValue(false);
    vi.mocked(getStoredAccessToken).mockReturnValue(null);

    render(<App />);

    expect(screen.queryByLabelText("Admin login")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Logout" })).not.toBeInTheDocument();
    expect(getCurrentAdmin).not.toHaveBeenCalled();
    expect(fetchProducts).toHaveBeenCalled();
  });

  it("does not install a login redirect handler when authentication is disabled", async () => {
    vi.mocked(isAuthEnabled).mockReturnValue(false);
    vi.mocked(getStoredAccessToken).mockReturnValue(null);

    render(<App />);
    await screen.findByRole("button", { name: "Products" });

    expect(setUnauthorizedHandler).toHaveBeenCalledWith(null);
    expect(screen.queryByLabelText("Admin login")).not.toBeInTheDocument();
  });

  it("renders navigation tabs", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suppliers" })).toBeInTheDocument();
    expect(screen.getByLabelText("Suggested demo flow")).toBeInTheDocument();
    expect(
      screen.getByText("Search and review the current product catalogue using our internal Product ID."),
    ).toBeInTheDocument();
    expect(screen.getByText("Search Product ID 3020 in Products.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unmapped Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weak Mappings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Mapping" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forecast" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Forecast" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Forecast Readiness" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Demand History" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Assignment Review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Cleanup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Purchase Orders" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recommendations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seasonality" })).toBeInTheDocument();
    expect(await screen.findByText("No products found.")).toBeInTheDocument();
  });

  it("edits supplier details locally and makes the lead time visible", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Suppliers" }));

    const workspace = await screen.findByLabelText("Supplier management workspace");
    expect(
      within(workspace).getByText(
        "Changes made here are saved in Purchasing AI only and are never sent to OrderPro.",
      ),
    ).toBeInTheDocument();
    expect(within(workspace).getByText("ED&F Man")).toBeInTheDocument();
    expect(within(workspace).getByText("2 active / 2 total")).toBeInTheDocument();

    await userEvent.click(within(workspace).getByRole("button", { name: "Edit" }));
    const editPanel = await screen.findByLabelText("Edit supplier");
    await userEvent.type(within(editPanel).getByLabelText("Lead time (days)"), "10");
    await userEvent.type(within(editPanel).getByLabelText("Payment terms"), "Net 30");
    await userEvent.click(within(editPanel).getByRole("button", { name: "Save supplier" }));

    expect(updateSupplier).toHaveBeenCalledWith(
      18,
      expect.objectContaining({
        email: "sales@edfman.test",
        lead_time_days: 10,
        payment_terms: "Net 30",
      }),
    );
    expect(await screen.findByText("ED&F Man supplier data saved in Purchasing AI.")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Supplier records")).getByText("10 days")).toBeInTheDocument();
  });

  it("forecast reconciliation summary, categories, and source labels render", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast Readiness" }));

    const summary = await screen.findByLabelText("Forecast readiness summary");
    expect(within(summary).getByText("Ready")).toBeInTheDocument();
    expect(within(summary).getByText("Blocked")).toBeInTheDocument();
    expect(within(summary).getByText("Monitor only")).toBeInTheDocument();
    expect(within(summary).getByText("Readiness %")).toBeInTheDocument();

    const table = await screen.findByLabelText("Forecast readiness rows");
    expect(within(table).getByText("Ready Product")).toBeInTheDocument();
    expect(within(table).getByText("READY-77")).toBeInTheDocument();
    expect(within(table).getByText("Missing Supplier Product")).toBeInTheDocument();
    expect(within(table).getByText("Monitor Only Product")).toBeInTheDocument();
    expect(within(table).getAllByText("OrderPro product cost")[0]).toBeInTheDocument();
    expect(within(table).getAllByText("Supplier record")[0]).toBeInTheDocument();
  });

  it("forecast reconciliation filters call the matching endpoint", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast Readiness" }));
    await screen.findByLabelText("Forecast readiness rows");
    await userEvent.selectOptions(screen.getByLabelText("Readiness status filter"), "blocked");
    await userEvent.selectOptions(screen.getByLabelText("Missing input filter"), "supplier_id");
    await userEvent.type(screen.getByLabelText("Search forecast readiness products"), "halter");

    expect(getForecastReconciliationProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({
        status: "blocked",
        missing_input: "supplier_id",
        search: "halter",
      }),
    );
  });

  it("forecast reconciliation detail links to supplier cleanup and forecast", async () => {
    vi.mocked(getForecastReconciliationProduct).mockResolvedValueOnce(
      mockForecastReconciliationProduct({
        product_id: 88,
        product_name: "Missing Supplier Product",
        supplier_id: null,
        supplier_name: null,
        supplier_source: "missing",
        readiness_status: "blocked",
        missing_inputs: ["supplier_id"],
        blocking_issues: ["missing_supplier"],
        explanation: "Supplier assignment is blocking forecast readiness.",
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast Readiness" }));
    await screen.findByText("Missing Supplier Product");
    await userEvent.click(screen.getAllByRole("button", { name: "Details" })[1]);

    const detail = await screen.findByLabelText("Forecast readiness detail");
    expect(within(detail).getByText("Supplier assignment is blocking forecast readiness.")).toBeInTheDocument();
    expect(within(detail).getByText("Missing")).toBeInTheDocument();

    await userEvent.click(within(detail).getByRole("button", { name: "Review Supplier" }));
    const cleanupWorkspace = await screen.findByLabelText("Manual supplier cleanup workspace");
    expect(within(cleanupWorkspace).getByRole("heading", { name: "Supplier Cleanup" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Forecast Readiness" }));
    await screen.findByText("Missing Supplier Product");
    await userEvent.click(screen.getAllByRole("button", { name: "Details" })[1]);
    await userEvent.click(await screen.findByRole("button", { name: "View Forecast" }));
    expect(await screen.findByLabelText("Product forecast")).toBeInTheDocument();
  });

  it("forecast reconciliation exports the current filter to CSV", async () => {
    const objectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:forecast-readiness");
    const revokeSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast Readiness" }));
    await screen.findByLabelText("Forecast readiness rows");
    await userEvent.selectOptions(screen.getByLabelText("Readiness status filter"), "ready");
    await userEvent.click(screen.getByRole("button", { name: "Export Readiness CSV" }));

    expect(exportForecastReconciliationCsv).toHaveBeenCalledWith(expect.objectContaining({ status: "ready" }));
    expect(objectUrlSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalledWith("blob:forecast-readiness");
    expect(await screen.findByText("Forecast readiness CSV exported.")).toBeInTheDocument();

    objectUrlSpy.mockRestore();
    revokeSpy.mockRestore();
  });

  it("demand history summary, import guidance, and product rows render", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Demand History" }));

    const summary = await screen.findByLabelText("Demand history summary");
    expect(within(summary).getByText("Products with history")).toBeInTheDocument();
    expect(within(summary).getByText("Products missing history")).toBeInTheDocument();
    expect(within(summary).getByText("Coverage %")).toBeInTheDocument();
    expect(screen.getByText("Local import commands")).toBeInTheDocument();

    const table = await screen.findByLabelText("Demand history products");
    expect(within(table).getByText("Demand Covered Product")).toBeInTheDocument();
    expect(within(table).getByText("DEMAND-7832")).toBeInTheDocument();
    expect(within(table).getByText("Missing History Product")).toBeInTheDocument();
    expect(within(table).getByText("Missing history")).toBeInTheDocument();
  });

  it("demand history filters call the coverage endpoint", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Demand History" }));
    await screen.findByLabelText("Demand history products");
    await userEvent.selectOptions(screen.getByLabelText("Demand history filter"), "missing_history");
    await userEvent.type(screen.getByLabelText("Search demand history products"), "halter");
    await userEvent.type(screen.getByLabelText("Demand history supplier filter"), "34");
    await userEvent.click(screen.getByLabelText("Recent demand"));

    expect(getDemandHistoryProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({
        has_history: false,
        search: "halter",
        supplier_id: 34,
        has_recent_demand: true,
      }),
    );
  });

  it("demand history detail displays monthly demand and readiness impact", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Demand History" }));
    await screen.findByText("Demand Covered Product");
    await userEvent.click(screen.getAllByRole("button", { name: "Details" })[0]);

    const detail = await screen.findByLabelText("Demand history detail");
    expect(getDemandHistoryProduct).toHaveBeenCalledWith(7832);
    expect(within(detail).getByText("Demand Covered Product")).toBeInTheDocument();
    expect(within(detail).getByText("Legacy usage history")).toBeInTheDocument();
    expect(within(detail).getByText("Demand history is present.")).toBeInTheDocument();
    expect(within(detail).getByText("2025-12")).toBeInTheDocument();
    expect(within(detail).getAllByText("12").length).toBeGreaterThan(0);
  });

  it("demand history export downloads the current coverage CSV", async () => {
    const objectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:demand-history");
    const revokeSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Demand History" }));
    await screen.findByLabelText("Demand history products");
    await userEvent.selectOptions(screen.getByLabelText("Demand history filter"), "with_history");
    await userEvent.click(screen.getByRole("button", { name: "Export Demand Coverage CSV" }));

    expect(exportDemandHistoryCsv).toHaveBeenCalledWith(expect.objectContaining({ has_history: true }));
    expect(objectUrlSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalledWith("blob:demand-history");
    expect(await screen.findByText("Demand coverage CSV exported.")).toBeInTheDocument();

    objectUrlSpy.mockRestore();
    revokeSpy.mockRestore();
  });

  it("supplier assignment review summary and suggested rows render", async () => {
    vi.mocked(getSupplierAssignmentReviewItems).mockResolvedValueOnce([
      mockSupplierAssignmentItem(),
      mockSupplierAssignmentItem({
        product_id: 8183,
        orderpro_sku: "NO-EVIDENCE",
        name: "No Evidence Product",
        suggested_supplier_id: null,
        suggested_supplier_name: null,
        suggestion_source: "none",
        confidence_label: "none",
        confidence_score: 0,
        status: "no_evidence",
        evidence_summary: { message: "No deterministic supplier evidence is available locally." },
        demand_history_available: false,
        open_customer_demand: 0,
      }),
      mockSupplierAssignmentItem({
        product_id: 8184,
        orderpro_sku: "EXPORT-SUP",
        name: "Export Suggested Product",
        suggestion_source: "orderpro_product_export",
        evidence_summary: { supplier_sku: "SUP-EXPORT-1" },
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Assignment Review" }));

    const summary = await screen.findByLabelText("Supplier assignment summary");
    expect(within(summary).getByText("Missing supplier")).toBeInTheDocument();
    expect(within(summary).getByText("PO evidence")).toBeInTheDocument();
    expect(screen.getByText("Missing Supplier Product")).toBeInTheDocument();
    expect(screen.getAllByText("Suggested Supplier").length).toBeGreaterThan(0);
    expect(screen.getByText("orderpro_product_export")).toBeInTheDocument();
    expect(screen.getByText("Supplier SKU: SUP-EXPORT-1")).toBeInTheDocument();
    expect(screen.getByText("No Evidence Product")).toBeInTheDocument();
    expect(screen.getByText("No deterministic supplier evidence is available locally.")).toBeInTheDocument();
    expect(
      screen.getByText("Review missing product suppliers using deterministic evidence. Confirmations are local only and are not pushed to OrderPro."),
    ).toBeInTheDocument();
  });

  it("supplier assignment confidence and demand filters call the endpoint", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Assignment Review" }));
    await screen.findByLabelText("Supplier assignment review rows");
    await userEvent.selectOptions(screen.getByLabelText("Confidence"), "high");
    await userEvent.click(screen.getByLabelText("Has demand"));

    expect(getSupplierAssignmentReviewItems).toHaveBeenLastCalledWith(
      expect.objectContaining({
        confidence: "high",
        has_demand: true,
      }),
    );
  });

  it("supplier assignment confirm suggestion calls the local confirm endpoint", async () => {
    vi.mocked(getSupplierAssignmentReviewItems).mockResolvedValue([mockSupplierAssignmentItem()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Assignment Review" }));
    await screen.findByText("Missing Supplier Product");
    await userEvent.click(screen.getByRole("button", { name: "Confirm suggestion" }));

    expect(confirmSupplierAssignmentReview).toHaveBeenCalledWith(
      8182,
      expect.objectContaining({ supplier_id: 34, reviewed_by: "manual" }),
    );
    expect(await screen.findByText("Supplier assignment confirmed locally.")).toBeInTheDocument();
  });

  it("supplier assignment reject asks for confirmation and calls reject endpoint", async () => {
    vi.mocked(getSupplierAssignmentReviewItems).mockResolvedValue([mockSupplierAssignmentItem()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Assignment Review" }));
    await screen.findByText("Missing Supplier Product");
    await userEvent.click(screen.getByRole("button", { name: "Reject suggestion" }));

    expect(window.confirm).toHaveBeenCalledWith("Reject this supplier assignment suggestion?");
    expect(rejectSupplierAssignmentReview).toHaveBeenCalledWith(
      8182,
      expect.objectContaining({ reviewed_by: "manual" }),
    );
  });

  it("manual supplier selection calls the confirm endpoint", async () => {
    vi.mocked(getSupplierAssignmentReviewItems).mockResolvedValue([
      mockSupplierAssignmentItem({
        suggested_supplier_id: null,
        suggested_supplier_name: null,
        confidence_label: "none",
        status: "no_evidence",
      }),
    ]);
    vi.mocked(listSuppliers).mockResolvedValue([
      mockSupplierOption(),
      mockSupplierOption({ id: 55, name: "Manual Supplier", orderpro_code: "MAN" }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Assignment Review" }));
    await screen.findByText("Missing Supplier Product");
    await userEvent.selectOptions(screen.getByLabelText("Manual supplier for Missing Supplier Product"), "55");
    await userEvent.click(screen.getByRole("button", { name: "Confirm manual supplier" }));

    expect(confirmSupplierAssignmentReview).toHaveBeenCalledWith(
      8182,
      expect.objectContaining({ supplier_id: 55, reviewed_by: "manual" }),
    );
  });

  it("manual supplier cleanup summary and candidate table render", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));

    const summary = await screen.findByLabelText("Manual supplier cleanup summary");
    expect(within(summary).getByText("Missing suppliers")).toBeInTheDocument();
    expect(within(summary).getByText("Priority candidates")).toBeInTheDocument();
    expect(screen.getByText("Cleanup Product")).toBeInTheDocument();
    expect(screen.getByText("CLEAN-71")).toBeInTheDocument();
    expect(screen.getByText(/This does not create suppliers or write back to OrderPro/)).toBeInTheDocument();
  });

  it("manual supplier cleanup filters and pagination call the API", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));
    await screen.findByLabelText("Manual supplier cleanup candidates");
    await userEvent.type(screen.getByLabelText("Search supplier cleanup products"), "halter");
    await userEvent.click(screen.getByLabelText("Priority only"));
    await userEvent.click(screen.getByLabelText("Open demand"));

    expect(getManualSupplierCleanupCandidates).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: "halter",
        priority_only: true,
        has_open_demand: true,
      }),
    );
  });

  it("manual supplier cleanup detail opens and supplier search works", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));
    await screen.findByText("Cleanup Product");
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await screen.findByLabelText("Supplier cleanup candidate detail");
    await userEvent.type(screen.getByLabelText("Search suppliers for cleanup"), "acme");

    expect(getManualSupplierCleanupCandidate).toHaveBeenCalledWith(71);
    expect(searchManualSupplierCleanupSuppliers).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: "acme", page_size: 25 }),
    );
    expect(screen.getByText("Recent PO evidence")).toBeInTheDocument();
  });

  it("manual supplier cleanup assignment confirms and removes the item", async () => {
    vi.mocked(getManualSupplierCleanupCandidates)
      .mockResolvedValueOnce({
        items: [mockCleanupCandidate()],
        page: 1,
        page_size: 25,
        total: 1,
        total_pages: 1,
        summary: {
          total_missing_supplier: 1,
          priority_candidates: 1,
          with_open_demand: 1,
          with_stock: 1,
          with_demand_history: 1,
          with_cost: 1,
        },
      })
      .mockResolvedValue({
        items: [],
        page: 1,
        page_size: 25,
        total: 0,
        total_pages: 0,
        summary: {
          total_missing_supplier: 0,
          priority_candidates: 0,
          with_open_demand: 0,
          with_stock: 0,
          with_demand_history: 0,
          with_cost: 0,
        },
      });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));
    await screen.findByText("Cleanup Product");
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await screen.findByLabelText("Supplier cleanup selected supplier");
    await userEvent.click(screen.getByRole("button", { name: "Assign supplier" }));

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Assign supplier \"Acme Supplies\""));
    expect(assignManualSupplierCleanupCandidate).toHaveBeenCalledWith(
      71,
      expect.objectContaining({ supplier_id: 10, reviewed_by: "Maged" }),
    );
    expect(await screen.findByText("Supplier assigned locally.")).toBeInTheDocument();
  });

  it("manual supplier cleanup records defer and reject reviews", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));
    await screen.findByText("Cleanup Product");
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await userEvent.click(await screen.findByRole("button", { name: "Defer" }));

    expect(reviewManualSupplierCleanupCandidate).toHaveBeenCalledWith(
      71,
      expect.objectContaining({ status: "deferred", reviewed_by: "Maged" }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reject suggestion" }));

    expect(reviewManualSupplierCleanupCandidate).toHaveBeenCalledWith(
      71,
      expect.objectContaining({ status: "rejected" }),
    );
  });

  it("manual supplier cleanup shows conflict errors", async () => {
    vi.mocked(assignManualSupplierCleanupCandidate).mockRejectedValue(new Error("Product already has a different supplier assignment."));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Cleanup" }));
    await screen.findByText("Cleanup Product");
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await userEvent.click(await screen.findByRole("button", { name: "Assign supplier" }));

    expect(await screen.findByText("Product already has a different supplier assignment.")).toBeInTheDocument();
  });

  it("seasonality summary cards display backend counts", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));

    const summary = await screen.findByLabelText("Seasonality summary cards");
    expect(within(summary).getByText("Total OrderPro products")).toBeInTheDocument();
    expect(within(summary).getByText("1484")).toBeInTheDocument();
    expect(within(summary).getByText("In season")).toBeInTheDocument();
    expect(within(summary).getByText("24")).toBeInTheDocument();
    expect(screen.getByText("Summer: 33")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Review seasonal sales patterns that may affect purchasing decisions. Seasonality is advisory and does not automatically change recommended purchase quantity.",
      ),
    ).toBeInTheDocument();
  });

  it("month selection sends the correct seasonality query", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));
    await screen.findByLabelText("Seasonality summary cards");
    await userEvent.selectOptions(screen.getByLabelText("Month"), "6");

    expect(getSeasonalitySummary).toHaveBeenLastCalledWith(6);
    expect(getSeasonalProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({ month: 6 }),
    );
  });

  it("seasonality filters call the products endpoint with selected filters", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));
    await screen.findByLabelText("Seasonality summary cards");
    await userEvent.selectOptions(screen.getByLabelText("Current status"), "in_season");
    await userEvent.selectOptions(screen.getByLabelText("Recurring tag"), "summer");
    await userEvent.type(screen.getByLabelText("Supplier ID"), "34");
    await userEvent.selectOptions(screen.getByLabelText("Confidence"), "high");

    expect(getSeasonalProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({
        status: "in_season",
        seasonality_tag: "summer",
        supplier_id: 34,
        min_confidence: "high",
      }),
    );
  });

  it("seasonal table displays warnings and sorts by seasonal priority", async () => {
    vi.mocked(getSeasonalProducts).mockResolvedValue([
      mockSeasonalProduct({
        product_id: 2,
        name: "Monitor Product",
        current_seasonality_status: "off_season",
        selected_month_index: 0.5,
        confidence_label: "low",
        current_stock: 12,
      }),
      mockSeasonalProduct({
        product_id: 1,
        name: "In Season Product",
        current_seasonality_status: "in_season",
        selected_month_index: 1.9,
        supplier_id: null,
        supplier_name: null,
        current_stock: 0,
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));

    const table = await screen.findByLabelText("Seasonal product table");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("In Season Product");
    expect(screen.getAllByText("Missing supplier").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Out of stock").length).toBeGreaterThan(0);
    expect(screen.getByText("Review manually")).toBeInTheDocument();
  });

  it("stock and quick filters narrow seasonal products on the client", async () => {
    vi.mocked(getSeasonalProducts).mockResolvedValue([
      mockSeasonalProduct({ name: "Stocked Summer", current_stock: 20 }),
      mockSeasonalProduct({ name: "Empty Summer", current_stock: 0 }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));
    await screen.findByText("Stocked Summer");
    await userEvent.selectOptions(screen.getByLabelText("Stock"), "out_of_stock");

    expect(screen.getByText("Empty Summer")).toBeInTheDocument();
    expect(screen.queryByText("Stocked Summer")).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Quick filter"), "in_season_out_of_stock");
    expect(screen.getByText("Empty Summer")).toBeInTheDocument();
  });

  it("product seasonality detail displays monthly values and reconciliation coverage", async () => {
    vi.mocked(getSeasonalProducts).mockResolvedValue([mockSeasonalProduct()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));
    await screen.findByText("Seasonal Fly Sheet");
    await userEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(getProductSeasonality).toHaveBeenCalledWith(7832, expect.any(Number));
    expect(await screen.findByText("June is part of this product's elevated demand period.")).toBeInTheDocument();
    const monthlyTable = screen.getByLabelText("Monthly seasonality values");
    expect(within(monthlyTable).getByText("June")).toBeInTheDocument();
    expect(within(monthlyTable).getByText("44")).toBeInTheDocument();
    expect(within(monthlyTable).getByText("1.8")).toBeInTheDocument();
    expect(screen.getByText("0 direct rows, 24 linked rows from 101, 102")).toBeInTheDocument();
    expect(screen.getByText("barcode_exact")).toBeInTheDocument();
  });

  it("forecast action opens forecast summary from a seasonal product", async () => {
    vi.mocked(getSeasonalProducts).mockResolvedValue([mockSeasonalProduct()]);
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        product_id: 7832,
        product_name: "Seasonal Fly Sheet",
        total_open_demand: 64,
        recommended_action: "reorder",
        recommended_qty: 64,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));
    await screen.findByText("Seasonal Fly Sheet");
    await userEvent.click(screen.getByRole("button", { name: "View Forecast" }));

    expect(fetchProductForecast).toHaveBeenCalledWith(7832);
    const forecastSummary = await screen.findByLabelText("Seasonality forecast summary");
    expect(within(forecastSummary).getAllByText("64").length).toBeGreaterThanOrEqual(2);
    expect(within(forecastSummary).getByText("reorder")).toBeInTheDocument();
    expect(
      within(forecastSummary).getByText(
        "Seasonality is currently advisory and does not automatically change the recommended purchase quantity.",
      ),
    ).toBeInTheDocument();
  });

  it("insufficient-data products are clearly labeled", async () => {
    vi.mocked(getSeasonalProducts).mockResolvedValue([
      mockSeasonalProduct({
        name: "Unknown Season Product",
        seasonality_tag: "insufficient_data",
        current_seasonality_status: "insufficient_data",
        confidence_label: "insufficient",
        selected_month_index: null,
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Seasonality" }));

    expect(await screen.findByText("Unknown Season Product")).toBeInTheDocument();
    expect(screen.getAllByText("Insufficient data").length).toBeGreaterThan(0);
  });

  it("existing PO workflows remain available and no API keys are requested", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supplier Forecast" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Purchase Orders" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recommendations" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument();
  });

  it("shows unmapped products with a clear review status", async () => {
    vi.mocked(fetchUnmappedProducts).mockResolvedValue([
      mockProduct({
        id: 2,
        name: "Unmapped Product",
        current_stock: 3,
        supplier_id: null,
        supplier_name: null,
        supplier_code: null,
        supplier_count: 0,
        preferred_supplier: null,
        preferred_supplier_id: null,
        preferred_supplier_sku: null,
        mapping_status: "unmapped",
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));

    expect(await screen.findByText("Unmapped Product")).toBeInTheDocument();
    expect(screen.getByText("Needs supplier mapping")).toBeInTheDocument();
    expect(screen.getByText("unmapped")).toBeInTheDocument();
  });

  it("displays a direct supplier as mapped even when legacy mappings are empty", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 12,
        name: "Direct Supplier Product",
        supplier_id: 34,
        supplier_name: "Direct OrderPro Supplier",
        supplier_code: "DOP",
        supplier_count: 0,
        preferred_supplier: null,
        preferred_supplier_id: null,
        supplier_mappings: [],
        mapping_status: "unmapped",
      }),
    ]);

    render(<App />);

    const row = (await screen.findByText("Direct Supplier Product")).closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Direct OrderPro Supplier")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("mapped")).toBeInTheDocument();
    expect(screen.getByLabelText("Select Direct Supplier Product for draft PO")).not.toBeDisabled();
  });

  it("renders a Products page search bar and loads the normal list when empty", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({ id: 3020, name: "Internal Product", orderpro_sku: "SKU-3020" }),
    ]);

    render(<App />);

    expect(
      await screen.findByPlaceholderText("Search by Product ID, SKU, barcode, or name"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Internal Product")).toBeInTheDocument();
    expect(fetchProducts).toHaveBeenCalledWith("");
  });

  it("Products page search sends the query to the backend and prioritizes internal product ID", async () => {
    vi.mocked(fetchProducts).mockImplementation(async (search?: string) => {
      if (search === "3020") {
        return [
          mockProduct({
            id: 3020,
            name: "Exact ID Product",
            orderpro_sku: "EXACT-ID-SKU",
          }),
        ];
      }
      return [
        mockProduct({
          id: 4000,
          name: "Numeric SKU Product",
          orderpro_sku: "3020",
        }),
      ];
    });

    render(<App />);
    expect(await screen.findByText("Numeric SKU Product")).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText("Search by Product ID, SKU, barcode, or name"),
      "3020",
    );

    await waitFor(() => expect(fetchProducts).toHaveBeenLastCalledWith("3020"));
    expect(await screen.findByText("Exact ID Product")).toBeInTheDocument();
    expect(screen.queryByText("Numeric SKU Product")).not.toBeInTheDocument();
    const row = screen.getByText("Exact ID Product").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("3020")).toBeInTheDocument();
  });

  it("global search does not conflict with Products page backend search", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 12,
        name: "Direct Supplier Product",
        supplier_id: 34,
        supplier_name: "Direct OrderPro Supplier",
        supplier_code: "DOP",
      }),
      mockProduct({
        id: 13,
        name: "Other Product",
        supplier_id: 35,
        supplier_name: "Other Supplier",
        supplier_code: "OTH",
      }),
    ]);

    render(<App />);
    await screen.findByText("Direct Supplier Product");
    await userEvent.type(screen.getByLabelText("Search"), "DOP");

    expect(screen.getByText("Direct Supplier Product")).toBeInTheDocument();
    expect(screen.getByText("Other Product")).toBeInTheDocument();
  });

  it("selects OrderPro-supplied products for draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 7,
        name: "Selectable Product",
        supplier_id: 6,
        supplier_name: "Draft Supplier",
        supplier_code: null,
      }),
    ]);

    render(<App />);

    await screen.findByText("Selectable Product");
    await userEvent.click(screen.getByLabelText("Select Selectable Product for draft PO"));

    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(screen.getByText("Product ID 7 - Selectable Product - Draft Supplier")).toBeInTheDocument();
    expect(screen.getByText("OrderPro supplier IDs in selection: 6")).toBeInTheDocument();
  });

  it("keeps generate draft PO disabled when no products are selected", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);

    render(<App />);

    await screen.findByText("Mapped Product");
    expect(screen.getByRole("button", { name: "Generate Draft PO" })).toBeDisabled();
    expect(
      screen.getByText("Select products with an OrderPro supplier from the table below."),
    ).toBeInTheDocument();
  });

  it("disables unmapped products for draft PO selection", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 8,
        name: "Unmapped Product",
        mapping_status: "unmapped",
        supplier_count: 0,
        preferred_supplier: null,
        preferred_supplier_id: null,
        supplier_id: null,
        supplier_name: null,
        supplier_code: null,
      }),
    ]);

    render(<App />);

    await screen.findByText("Unmapped Product");
    expect(screen.getByLabelText("Select Unmapped Product for draft PO")).toBeDisabled();
  });

  it("generates draft POs from product IDs and displays the result", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      mockProduct({
        id: 7,
        name: "Mapped Product",
        supplier_id: 6,
        supplier_name: "Supplier One",
      }),
    ]);
    vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue(
      mockDraftFromProductsResponse({ id: 501, status: "draft" }),
    );

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(createDraftPurchaseOrderFromProducts).toHaveBeenCalledWith({
      product_ids: [7],
      created_by: "manual",
      notes: "Draft generated from product selection",
      only_reorder_needed: false,
    });
    const resultPanel = await screen.findByLabelText("Draft PO generation result");
    expect(within(resultPanel).getByText("1 draft PO created")).toBeInTheDocument();
    expect(within(resultPanel).getByText(/Draft PO 501:/)).toBeInTheDocument();
    expect(within(resultPanel).getByText("draft")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View Draft PO 501" })).toBeInTheDocument();
  });

  it("displays skipped product summary after draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);
    const purchaseOrder = mockPurchaseOrder({ id: 502, status: "draft" });
    vi.mocked(createDraftPurchaseOrderFromProducts).mockResolvedValue({
      purchase_order: purchaseOrder,
      created_purchase_orders: [purchaseOrder],
      summary: {
        created_po_count: 1,
        created_line_count: 1,
        grouped_by_supplier: { "10": 1 },
        skipped_products: [
          {
            product_id: 9,
            product_name: "Skipped Product",
            reason: "Product is missing an OrderPro supplier mapping.",
          },
        ],
      },
    });

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(await screen.findByText("Skipped Products")).toBeInTheDocument();
    expect(
      screen.getByText("Skipped Product: Product is missing an OrderPro supplier mapping."),
    ).toBeInTheDocument();
  });

  it("displays backend errors from draft PO generation", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([mockProduct({ id: 7, name: "Mapped Product" })]);
    vi.mocked(createDraftPurchaseOrderFromProducts).mockRejectedValue(
      new Error("No valid purchase order lines could be created."),
    );

    render(<App />);

    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByLabelText("Select Mapped Product for draft PO"));
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO" }));

    expect(
      await screen.findByText(
        "Draft generation failed: No valid purchase order lines could be created.",
      ),
    ).toBeInTheDocument();
  });

  it("shows supplier mapping product and supplier fields", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));

    expect(await screen.findByText("Mapped Product")).toBeInTheDocument();
    expect(screen.getByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("ACME-1")).toBeInTheDocument();
    expect(screen.getByText("Acme Product Pack")).toBeInTheDocument();
    expect(screen.getByText("matched")).toBeInTheDocument();
    expect(screen.getByText("sku")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Legacy ProductSupplier mappings are transitional. Active purchasing now uses the OrderPro supplier on each product.",
      ),
    ).toBeInTheDocument();
  });

  it("renders empty states safely for review tabs", async () => {
    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: "Weak Mappings" }));
    expect(await screen.findByText("No weak mappings found.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));
    expect(await screen.findByText("No supplier mappings found.")).toBeInTheDocument();
  });

  it("shows weak mapping review details when available", async () => {
    vi.mocked(fetchWeakMappings).mockResolvedValue([mockWeakMapping()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Weak Mappings" }));

    expect(await screen.findByText("Questionable Product")).toBeInTheDocument();
    expect(screen.getByText("Maybe Supplier")).toBeInTheDocument();
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
    expect(screen.getByText("MAYBE-2")).toBeInTheDocument();
  });

  it("renders supplier context for a product forecast", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("Mapped Product")).toBeInTheDocument();
    expect(screen.getByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("ACME-1")).toBeInTheDocument();
    expect(screen.getByText("Acme Product Pack")).toBeInTheDocument();
    expect(screen.getByText("9.5 USD")).toBeInTheDocument();
    expect(screen.getByText("OrderPro product supplier")).toBeInTheDocument();
    expect(screen.getByText("6 (product_supplier)")).toBeInTheDocument();
  });

  it("does not crash when supplier context is missing", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(mockForecast({ supplier_context: null }));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("No supplier context returned.")).toBeInTheDocument();
  });

  it("shows inbound stock and before/after reorder quantities on product forecast", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        incoming_qty: 20,
        effective_available_stock_for_reorder: 8,
        recommended_qty_before_inbound: 64,
        recommended_qty_after_inbound: 44,
        recommended_qty: 44,
        inbound_adjustment_qty: 20,
        incoming_stock_context: {
          product_id: 1,
          incoming_qty: 20,
          incoming_qty_local: 5,
          incoming_qty_orderpro: 15,
          incoming_qty_total: 20,
          incoming_qty_by_source: { local_purchase_orders: 5, orderpro_purchase_orders: 15 },
          source_breakdown: {
            local_purchase_orders: { incoming_qty: 5, open_po_line_count: 1 },
            orderpro_purchase_orders: { incoming_qty: 15, open_po_line_count: 1 },
          },
          open_po_count: 2,
          open_po_line_count: 2,
          earliest_expected_date: null,
          latest_expected_date: null,
          supplier_ids: [10],
          warnings: ["Line-level received/cancelled quantities are unavailable; full open line quantity is counted."],
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("Incoming Stock")).toBeInTheDocument();
    expect(screen.getByText("Total incoming")).toBeInTheDocument();
    expect(screen.getByText("Local incoming")).toBeInTheDocument();
    expect(screen.getByText("OrderPro incoming")).toBeInTheDocument();
    expect(screen.getByText("Recommended before inbound")).toBeInTheDocument();
    expect(screen.getByText("Inbound adjustment")).toBeInTheDocument();
    expect(screen.getByText("Line-level received/cancelled quantities are unavailable; full open line quantity is counted.")).toBeInTheDocument();
  });

  it("shows raw to pack-rounded quantity context on product forecast", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        raw_required_quantity: 57,
        pre_pack_recommended_quantity: 57,
        order_multiple: 56,
        pack_rule_name: "Uniblock default",
        pack_rule_source: "product_pack_rule",
        pack_rule_display: "112 units = 2 pallets (56 each)",
        pack_rounding_explanation: "57 raw -> 112 final using 56 order multiple",
        pack_rule_warnings: ["Reviewed pack rule."],
        recommended_qty: 112,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("Raw required quantity")).toBeInTheDocument();
    expect(screen.getByText("Order multiple")).toBeInTheDocument();
    expect(screen.getByText("Uniblock default")).toBeInTheDocument();
    expect(screen.getByText("57 raw -> 112 final using 56 order multiple")).toBeInTheDocument();
    expect(screen.getByText("112 units = 2 pallets (56 each)")).toBeInTheDocument();
    expect(screen.getByText("Reviewed pack rule.")).toBeInTheDocument();
  });

  it("shows a warning when supplier mapping is needed", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        supplier_context: {
          supplier_id: null,
          supplier_name: null,
          supplier_sku: null,
          supplier_product_name: null,
          purchase_price: null,
          currency: null,
          lead_time_days: 0,
          lead_time_source: "missing",
          minimum_order_quantity: 0,
          moq_source: "missing",
          match_status: null,
          match_method: null,
          mapping_source: "missing",
          has_supplier_mapping: false,
          needs_supplier_mapping: true,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(
      await screen.findByText(
        "This product needs supplier mapping before purchasing recommendations can be trusted.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing supplier mapping")).toBeInTheDocument();
  });

  it("does not show a missing-supplier warning when forecast context has a direct supplier", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        supplier_context: {
          supplier_id: 10,
          supplier_name: "Direct Forecast Supplier",
          supplier_code: "DFS",
          supplier_sku: "DFS-1",
          supplier_product_name: null,
          purchase_price: null,
          currency: null,
          lead_time_days: 4,
          lead_time_source: "product_record",
          minimum_order_quantity: 1,
          moq_source: "product_record",
          match_status: "mapped",
          match_method: "orderpro_product_supplier",
          mapping_source: "orderpro_product_supplier",
          has_supplier_mapping: true,
          needs_supplier_mapping: true,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("Direct Forecast Supplier")).toBeInTheDocument();
    expect(
      screen.queryByText(
        "This product needs supplier mapping before purchasing recommendations can be trusted.",
      ),
    ).not.toBeInTheDocument();
  });

  it("labels fallback supplier mapping sources clearly", async () => {
    vi.mocked(fetchProductForecast).mockResolvedValue(
      mockForecast({
        supplier_context: {
          supplier_id: 11,
          supplier_name: "Fallback Supplier",
          supplier_sku: "FALLBACK-1",
          supplier_product_name: "Fallback Product",
          purchase_price: null,
          currency: null,
          lead_time_days: 5,
          lead_time_source: "supplier_master",
          minimum_order_quantity: 2,
          moq_source: "product_record",
          match_status: "matched",
          match_method: "import_match",
          mapping_source: "product_master_item",
          has_supplier_mapping: true,
          needs_supplier_mapping: false,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Forecast" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Fetch Forecast" }));

    expect(await screen.findByText("ProductMasterItem fallback")).toBeInTheDocument();
    expect(screen.getByText("Fallback Supplier")).toBeInTheDocument();
  });

  it("confirm button calls the confirm endpoint and refreshes mappings", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(confirmProductSupplier).toHaveBeenCalledWith(100);
    expect(fetchProductSuppliers).toHaveBeenCalledTimes(2);
  });

  it("reject button confirms before calling the reject endpoint", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(window.confirm).toHaveBeenCalledWith("Reject this supplier mapping?");
    expect(rejectProductSupplier).toHaveBeenCalledWith(100);
  });

  it("set preferred button calls the set-preferred endpoint", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([mockSupplierMapping({ is_preferred: false })]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "Set Preferred" }));

    expect(setPreferredProductSupplier).toHaveBeenCalledWith(100);
  });

  it("validates product_id and supplier_id before creating a mapping", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(await screen.findByText("Product ID is required.")).toBeInTheDocument();
    expect(createProductSupplier).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Product ID"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(await screen.findByText("Supplier ID is required.")).toBeInTheDocument();
    expect(createProductSupplier).not.toHaveBeenCalled();
  });

  it("creates mapping with default manual review fields", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Unmapped Products" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "2");
    await userEvent.type(screen.getByLabelText("Supplier ID"), "3");
    await userEvent.type(screen.getByLabelText("Supplier SKU"), "NEW-SKU");
    await userEvent.click(screen.getByRole("button", { name: "Create Mapping" }));

    expect(createProductSupplier).toHaveBeenCalledWith(
      expect.objectContaining({
        product_id: 2,
        supplier_id: 3,
        supplier_sku: "NEW-SKU",
        match_status: "needs_review",
        match_method: "manual",
      }),
    );
  });

  it("displays rejected mapping status distinctly", async () => {
    vi.mocked(fetchProductSuppliers).mockResolvedValue([
      mockSupplierMapping({ is_preferred: false, match_status: "rejected" }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Mapping" }));

    const rejected = await screen.findByText("rejected");
    expect(rejected).toHaveClass("rejected");
  });

  it("purchase orders tab renders and lists a draft PO", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));

    expect(await screen.findByText("Acme Supplies")).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.getByText("Draft PO")).toBeInTheDocument();
    expect(screen.getByText("19")).toBeInTheDocument();
  });

  it("export CSV button renders on a purchase order with line items", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Export Clean CSV" })).toBeEnabled();
  });

  it("export CSV button is disabled for an empty purchase order", async () => {
    const emptyPo = mockPurchaseOrder({ lines: [] });
    vi.mocked(listPurchaseOrders).mockResolvedValue([emptyPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(emptyPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Export Clean CSV" })).toBeDisabled();
    expect(screen.getByText("Add at least one line before exporting CSV.")).toBeInTheDocument();
  });

  it("export CSV action downloads the returned blob with the response filename", async () => {
    const objectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:purchase-order");
    const revokeSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(exportPurchaseOrderCsv).mockResolvedValue({
      blob: new Blob(["csv"], { type: "text/csv" }),
      filename: "PO-500_Acme.csv",
    });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Export Clean CSV" }));

    expect(exportPurchaseOrderCsv).toHaveBeenCalledWith(500);
    expect(objectUrlSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalledWith("blob:purchase-order");
    expect(await screen.findByText("Clean purchase order CSV exported.")).toBeInTheDocument();
  });

  it("export CSV action uses fallback filename when the header filename is absent", async () => {
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(this.download).toBe("PO-500.csv");
      });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fallback");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(exportPurchaseOrderCsv).mockResolvedValue({
      blob: new Blob(["csv"], { type: "text/csv" }),
      filename: null,
    });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Export Clean CSV" }));

    expect(clickSpy).toHaveBeenCalled();
  });

  it("export CSV button shows exporting state while waiting", async () => {
    let resolveExport: (value: { blob: Blob; filename: string | null }) => void = () => {};
    vi.mocked(exportPurchaseOrderCsv).mockReturnValue(
      new Promise((resolve) => {
        resolveExport = resolve;
      }),
    );
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Export Clean CSV" }));

    expect(await screen.findByRole("button", { name: "Exporting..." })).toBeDisabled();
    resolveExport({ blob: new Blob(["csv"]), filename: "done.csv" });
  });

  it("export CSV errors show a user-facing message", async () => {
    vi.mocked(exportPurchaseOrderCsv).mockRejectedValue(new Error("Purchase order not found."));
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Export Clean CSV" }));

    expect(
      await screen.findByText(
        "Purchase order action failed: Could not export purchase order CSV. Purchase order not found.",
      ),
    ).toBeInTheDocument();
  });

  it("shows handoff packet download only for issued purchase orders", async () => {
    const issuedPo = mockPurchaseOrder({
      status: "issued",
      issued_at: "2026-05-28T12:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);

    const { unmount } = render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Download handoff packet" })).toBeEnabled();
    expect(
      screen.getByText("Downloading the handoff packet does not send the PO externally or create an OrderPro purchase order."),
    ).toBeInTheDocument();

    unmount();
    const draftPo = mockPurchaseOrder({ status: "draft", issued_at: null });
    vi.mocked(listPurchaseOrders).mockResolvedValue([draftPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(draftPo);
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));

    expect(screen.queryByRole("button", { name: "Download handoff packet" })).not.toBeInTheDocument();
  });

  it("handoff packet action downloads the returned zip without external-send wording", async () => {
    const objectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:purchase-order-handoff");
    const revokeSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(this.download).toBe("purchase-order-po-500-handoff.zip");
      });
    const issuedPo = mockPurchaseOrder({
      status: "issued",
      issued_at: "2026-05-28T12:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);
    vi.mocked(exportPurchaseOrderHandoffPacket).mockResolvedValue({
      blob: new Blob(["zip"], { type: "application/zip" }),
      filename: "purchase-order-po-500-handoff.zip",
    });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(await screen.findByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Download handoff packet" }));

    expect(exportPurchaseOrderHandoffPacket).toHaveBeenCalledWith(500);
    expect(objectUrlSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalledWith("blob:purchase-order-handoff");
    expect(
      await screen.findByText("Purchase order handoff packet downloaded. Nothing was sent externally."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send/i })).not.toBeInTheDocument();
  });

  it("create draft PO form validates supplier_id", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await userEvent.click(screen.getByRole("button", { name: "Create Draft PO" }));

    expect(await screen.findByText("Supplier ID is required.")).toBeInTheDocument();
    expect(createPurchaseOrder).not.toHaveBeenCalled();
  });

  it("add line form validates product ID and quantity", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(await screen.findByText("Product ID is required.")).toBeInTheDocument();
    expect(addPurchaseOrderLine).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Product ID"), "100");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(await screen.findByText("Quantity must be greater than zero.")).toBeInTheDocument();
    expect(addPurchaseOrderLine).not.toHaveBeenCalled();
  });

  it("shows backend error when adding an invalid PO line", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(addPurchaseOrderLine).mockRejectedValue(
      new Error("Product belongs to a different OrderPro supplier."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "101");
    await userEvent.type(screen.getByLabelText("Quantity"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Add Line" }));

    expect(addPurchaseOrderLine).toHaveBeenCalledWith(500, {
      product_id: 101,
      quantity: 3,
      notes: null,
    });
    expect(
      await screen.findByText(
        "Purchase order action failed: Product belongs to a different OrderPro supplier.",
      ),
    ).toBeInTheDocument();
  });

  it("loads supplier stock by supplier and exposes the full supplier forecast", async () => {
    vi.mocked(listSuppliers).mockResolvedValue([
      mockSupplierOption({ id: 53, name: "Forecast Supplier", orderpro_code: "FORECAST" }),
    ]);
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        supplier_id: 53,
        supplier_name: "Forecast Supplier",
        supplier_code: "FORECAST",
        stock_status: "critical",
        total_current_stock: 5,
        low_stock_products: [77],
        products_needing_reorder: [77],
        high_risk_products: [77],
        forecasts: [
          mockForecast({
            product_id: 77,
            orderpro_sku: "OP-77",
            product_name: "Low Stock Product",
            current_stock: 5,
            reorder_point: 12,
            recommended_qty: 8,
            risk_level: "high",
            inventory_last_synced_at: "2026-08-24T08:00:00",
          }),
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Stock" }));
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier stock supplier"),
      "53",
    );

    expect(getSupplierForecast).toHaveBeenCalledWith(53);
    expect(await screen.findByText("Critical stock risk")).toBeInTheDocument();
    expect(screen.getByText("Low Stock Product")).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Supplier stock rows")).getByText("Critical"),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "View Full Supplier Forecast" }));
    expect(await screen.findByDisplayValue("53")).toBeInTheDocument();
    expect(getSupplierForecast).toHaveBeenCalledWith(53);
  });

  it("refreshes OrderPro stock locally and reloads the selected supplier", async () => {
    vi.mocked(listSuppliers).mockResolvedValue([
      mockSupplierOption({ id: 53, name: "Forecast Supplier", orderpro_code: "FORECAST" }),
    ]);
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({ supplier_id: 53, supplier_name: "Forecast Supplier" }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Stock" }));
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier stock supplier"),
      "53",
    );
    await screen.findByRole("heading", { name: "Forecast Supplier" });
    await userEvent.click(screen.getByRole("button", { name: "Refresh Stock from OrderPro" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Refresh current stock from OrderPro? This reads OrderPro and updates only Purchasing AI's local stock cache.",
    );
    expect(refreshOrderProInventory).toHaveBeenCalledTimes(1);
    expect(getSupplierForecast).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/OrderPro stock refresh completed/)).toBeInTheDocument();
  });

  it("shows stocked products that still need a canonical supplier assignment", async () => {
    vi.mocked(fetchUnmappedProducts).mockResolvedValue([
      mockProduct({
        id: 8182,
        orderpro_sku: "UNASSIGNED-8182",
        name: "Unassigned Stock Product",
        supplier_id: null,
        current_stock: 4,
      }),
    ]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Stock" }));
    await userEvent.selectOptions(
      await screen.findByLabelText("Supplier stock supplier"),
      "unassigned",
    );

    expect(await screen.findByText("Unassigned Stock Product")).toBeInTheDocument();
    expect(screen.getByText("Needs supplier mapping")).toBeInTheDocument();
    expect(screen.getByText(/supplier forecast cannot be generated/)).toBeInTheDocument();
  });

  it("supplier forecast page calls the supplier forecast endpoint and displays product rows", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        supplier_name: "Forecast Supplier",
        product_count: 1,
        forecasts: [
          mockForecast({
            product_id: 77,
            orderpro_sku: "OP-77",
            product_name: "Forecasted Product",
            current_stock: 5,
            effective_available_stock: 0,
            shipped_units_in_window: 18,
            avg_daily_usage: 3,
            open_confirmed_units: 64,
            open_packed_units: 2,
            open_backorder_units: 1,
            total_open_demand: 67,
            lead_time_days_used: 4,
            reorder_point: 12,
            demand_source: "orderpro_orders",
            recommended_action: "reorder",
            recommended_qty: 8,
            risk_level: "high",
            explanation: "Open committed demand exceeds current stock.",
          }),
        ],
        products_needing_reorder: [77],
        total_recommended_quantity: 8,
        total_estimated_cost: 80,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));

    expect(getSupplierForecast).toHaveBeenCalledWith(53);
    expect(await screen.findByText("Forecast Supplier")).toBeInTheDocument();
    expect(screen.getByText("Forecasted Product")).toBeInTheDocument();
    expect(screen.getByText("OP-77")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText("OrderPro orders")).toBeInTheDocument();
    expect(screen.getByText("Open committed demand exceeds current stock.")).toBeInTheDocument();
    expect(screen.getByText("reorder")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
  });

  it("supplier forecast displays empty and monitor states", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        forecasts: [
          mockForecast({
            demand_source: "none",
            shipped_order_count: 0,
            recommended_action: "monitor",
            recommended_qty: 0,
          }),
        ],
        products_needing_reorder: [],
        total_recommended_quantity: 0,
        total_estimated_cost: null,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));

    expect(
      await screen.findByText(
        "Forecast incomplete: zero recommended quantity is not a safe no-order decision until the missing inputs are resolved.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "1 product(s) have no usable demand history; their zero recommendation is not a purchase decision.",
      ),
    ).toBeInTheDocument();
  });

  it("orders supplier forecast rows by reorder risk and quantity", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        forecasts: [
          mockForecast({ product_id: 1, product_name: "Monitor Product", recommended_action: "monitor", recommended_qty: 0, risk_level: "low" }),
          mockForecast({ product_id: 2, product_name: "Small Reorder", recommended_action: "reorder", recommended_qty: 4, risk_level: "medium" }),
          mockForecast({ product_id: 3, product_name: "Large Reorder", recommended_action: "reorder", recommended_qty: 12, risk_level: "high" }),
        ],
        products_needing_reorder: [2, 3],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));

    const table = await screen.findByLabelText("Supplier forecast rows");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Large Reorder");
    expect(rows[2]).toHaveTextContent("Small Reorder");
    expect(rows[3]).toHaveTextContent("Monitor Product");
  });

  it("supplier forecast displays inbound stock before and after recommendation fields", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        forecasts: [
          mockForecast({
            product_id: 1,
            product_name: "Inbound Covered Product",
            incoming_qty: 20,
            recommended_qty_before_inbound: 64,
            recommended_qty: 44,
          }),
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));

    const table = await screen.findByLabelText("Supplier forecast rows");
    expect(within(table).getByText("Incoming")).toBeInTheDocument();
    expect(within(table).getByText("Before inbound")).toBeInTheDocument();
    expect(within(table).getByText("20")).toBeInTheDocument();
    expect(within(table).getByText("64")).toBeInTheDocument();
    expect(within(table).getByText("44")).toBeInTheDocument();
  });

  it("filters supplier forecast by high risk and open demand", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        forecasts: [
          mockForecast({ product_id: 1, product_name: "Open High Product", recommended_qty: 64, risk_level: "high", total_open_demand: 64 }),
          mockForecast({ product_id: 2, product_name: "Quiet Product", recommended_qty: 0, risk_level: "low", total_open_demand: 0 }),
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("Open High Product");

    await userEvent.click(screen.getByRole("button", { name: "High risk" }));
    expect(screen.getByText("Open High Product")).toBeInTheDocument();
    expect(screen.queryByText("Quiet Product")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Open demand" }));
    expect(screen.getByText("Open High Product")).toBeInTheDocument();
    expect(screen.queryByText("Quiet Product")).not.toBeInTheDocument();
  });

  it("filters supplier forecast by no demand history and missing lead time", async () => {
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        forecasts: [
          mockForecast({
            product_id: 1,
            product_name: "No History Product",
            demand_source: "none",
            shipped_order_count: 0,
            recommended_qty: 0,
          }),
          mockForecast({
            product_id: 2,
            product_name: "Missing Lead Product",
            lead_time_days_used: 0,
            lead_time_source: "missing",
            recommended_action: "needs_supplier_mapping",
          }),
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("No History Product");
    expect(
      screen.getByText(
        "1 product(s) are missing lead time; their reorder quantities cannot be calculated yet.",
      ),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "No demand history" }));
    expect(screen.getByText("No History Product")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Missing lead time" }));
    expect(screen.getByText("Missing Lead Product")).toBeInTheDocument();
    expect(screen.queryByText("No History Product")).not.toBeInTheDocument();
  });

  it("generates a supplier forecast draft PO after confirmation", async () => {
    const purchaseOrder = mockPurchaseOrder({
      id: 777,
      status: "draft",
      lines: [
        {
          ...mockPurchaseOrder().lines[0],
          product_id: 77,
          quantity: 64,
        },
      ],
    });
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({
        supplier_id: 53,
        supplier_name: "Forecast Supplier",
        products_needing_reorder: [77],
        forecasts: [mockForecast({ product_id: 77, recommended_action: "reorder", recommended_qty: 64 })],
      }),
    );
    vi.mocked(createDraftPOFromSupplierForecast).mockResolvedValue({
      purchase_order: purchaseOrder,
      created_purchase_orders: [purchaseOrder],
      summary: {
        created_po_count: 1,
        created_line_count: 1,
        skipped_products: [],
        grouped_by_supplier: { "53": 1 },
      },
    });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("Forecast Supplier");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO from Supplier Forecast" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Generate a draft PO from this supplier forecast? Only products with recommended quantity greater than zero will be included. This creates a draft only; it will not be approved, issued, or sent to OrderPro.",
    );
    expect(createDraftPOFromSupplierForecast).toHaveBeenCalledWith(53, {
      created_by: "manual",
      notes: "Draft generated from supplier forecast",
      only_reorder_needed: true,
    });
    expect(await screen.findByText("1 draft PO created")).toBeInTheDocument();
    expect(screen.getByText(/Draft PO 777:/)).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Draft PO generation result")).getByText("64")).toBeInTheDocument();
  });

  it("does not call supplier forecast draft generation when confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValueOnce(false);
    vi.mocked(getSupplierForecast).mockResolvedValue(
      mockSupplierForecast({ products_needing_reorder: [1] }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO from Supplier Forecast" }));

    expect(createDraftPOFromSupplierForecast).not.toHaveBeenCalled();
  });

  it("shows supplier forecast draft backend errors", async () => {
    vi.mocked(createDraftPOFromSupplierForecast).mockRejectedValue(
      new Error("No products need reorder for this supplier."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO from Supplier Forecast" }));

    expect(
      await screen.findByText(
        "Supplier forecast draft generation failed: No products need reorder for this supplier.",
      ),
    ).toBeInTheDocument();
  });

  it("does not display a created PO when supplier forecast draft result is empty", async () => {
    vi.mocked(createDraftPOFromSupplierForecast).mockResolvedValue({
      purchase_order: null,
      created_purchase_orders: [],
      summary: {
        created_po_count: 0,
        created_line_count: 0,
        skipped_products: [],
        grouped_by_supplier: null,
      },
    });

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    await userEvent.type(screen.getByLabelText("Supplier ID"), "53");
    await userEvent.click(screen.getByRole("button", { name: "Load Supplier Forecast" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "Generate Draft PO from Supplier Forecast" }));

    expect(await screen.findByText("0 draft POs created")).toBeInTheDocument();
    expect(screen.getByText("No draft purchase order was created.")).toBeInTheDocument();
    expect(screen.queryByText(/Draft PO \d+:/)).not.toBeInTheDocument();
  });

  it("keeps product-based PO generation available separately and does not request API keys", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Generate Draft PO" })).toBeInTheDocument();
    expect(screen.queryByText(/api key/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Supplier Forecast" }));
    expect(screen.getByRole("button", { name: "Load Supplier Forecast" })).toBeInTheDocument();
    expect(screen.queryByText(/api key/i)).not.toBeInTheDocument();
  });

  it("submit for approval calls the correct endpoint", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Submit for Approval" }));

    expect(submitPurchaseOrderForApproval).toHaveBeenCalledWith(500);
  });

  it("shows purchase order preflight warnings in PO detail", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(
      mockPurchaseOrderPreflight({
        warnings: ["Missing cost; review before ordering."],
        line_checks: [
          {
            ...mockPurchaseOrderPreflight().line_checks[0],
            warnings: ["Missing cost; review before ordering."],
          },
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("heading", { name: "PO Preflight" })).toBeInTheDocument();
    expect(screen.getByText("Review before moving forward.")).toBeInTheDocument();
    expect(screen.getAllByText("Missing cost; review before ordering.").length).toBeGreaterThan(0);
  });

  it("disables submit when PO preflight has blockers", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(
      mockPurchaseOrderPreflight({
        can_submit: false,
        overall_status: "blocked",
        blockers: ["Line quantity must be greater than zero."],
        warnings: [],
        line_checks: [
          {
            ...mockPurchaseOrderPreflight().line_checks[0],
            blockers: ["Line quantity must be greater than zero."],
            warnings: [],
          },
        ],
        summary_counts: {
          line_count: 1,
          blocker_count: 1,
          warning_count: 0,
          lines_with_blockers: 1,
          lines_with_warnings: 0,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    const submitButton = await screen.findByRole("button", { name: "Submit for Approval" });
    await waitFor(() => expect(submitButton).toBeDisabled());
    expect(screen.getByText("This PO cannot move forward yet.")).toBeInTheDocument();
    expect(screen.getAllByText("Line quantity must be greater than zero.").length).toBeGreaterThan(0);
  });

  it("cancel purchase order asks for confirmation", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(window.confirm).toHaveBeenCalledWith("Cancel this purchase order?");
    expect(cancelPurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("pending approval PO shows approve action and hides line editing", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("approved PO shows issue action and no line editing", async () => {
    const approvedPo = mockPurchaseOrder({
      status: "approved",
      approved_at: "2026-05-28T11:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([approvedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(approvedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Mark as locally issued" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Marking this PO as locally issued only changes the local status. It does not send to OrderPro, email suppliers, or create an external PO.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
  });

  it("shows external send readiness as not implemented and no Send to OrderPro action", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("heading", { name: "External Send Readiness" })).toBeInTheDocument();
    expect(
      screen.getAllByText("This purchase order is local-only. External OrderPro sending is not implemented yet.").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Target system")).toBeInTheDocument();
    expect(screen.getByText("OrderPro")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send to orderpro/i })).not.toBeInTheDocument();
  });

  it("issued PO shows receive action and no line editing", async () => {
    const issuedPo = mockPurchaseOrder({
      status: "issued",
      approved_at: "2026-05-28T11:00:00",
      issued_at: "2026-05-28T12:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Receive" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Line" })).not.toBeInTheDocument();
  });

  it("received PO shows no workflow action buttons", async () => {
    const receivedPo = mockPurchaseOrder({
      status: "received",
      approved_at: "2026-05-28T11:00:00",
      issued_at: "2026-05-28T12:00:00",
      received_at: "2026-05-28T13:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([receivedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(receivedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");

    expect(screen.queryByRole("button", { name: "Submit for Approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as locally issued" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Receive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("cancelled PO shows no workflow action buttons", async () => {
    const cancelledPo = mockPurchaseOrder({
      status: "cancelled",
      cancelled_at: "2026-05-28T11:00:00",
    });
    vi.mocked(listPurchaseOrders).mockResolvedValue([cancelledPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(cancelledPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Purchase Order 500");

    expect(screen.queryByRole("button", { name: "Submit for Approval" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as locally issued" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Receive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("approve action calls the approve endpoint with approved_by", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);
    vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(
      mockPurchaseOrderPreflight({
        status: "pending_approval",
        can_submit: false,
        can_approve: true,
        overall_status: "ready",
        warnings: [],
        line_checks: [],
        summary_counts: {
          line_count: 1,
          blocker_count: 0,
          warning_count: 0,
          lines_with_blockers: 0,
          lines_with_warnings: 0,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.type(await screen.findByLabelText("Approved by"), "manager");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(approvePurchaseOrder).toHaveBeenCalledWith(500, { approved_by: "manager" });
  });

  it("disables approve when PO preflight blocks approval", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);
    vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(
      mockPurchaseOrderPreflight({
        status: "pending_approval",
        can_submit: false,
        can_approve: false,
        overall_status: "blocked",
        blockers: ["Purchase order has no lines."],
        warnings: [],
        line_checks: [],
        summary_counts: {
          line_count: 0,
          blocker_count: 1,
          warning_count: 0,
          lines_with_blockers: 0,
          lines_with_warnings: 0,
        },
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    const approveButton = await screen.findByRole("button", { name: "Approve" });
    await waitFor(() => expect(approveButton).toBeDisabled());
    expect(screen.getByText("Purchase order has no lines.")).toBeInTheDocument();
  });

  it("shows non-blocking message when PO preflight cannot load", async () => {
    vi.mocked(listPurchaseOrders).mockResolvedValue([mockPurchaseOrder()]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(mockPurchaseOrder());
    vi.mocked(getPurchaseOrderPreflight).mockRejectedValue(new Error("Preflight unavailable."));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(
      await screen.findByText(
        "Preflight is unavailable right now. Backend validation will still run before any status change.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit for Approval" })).toBeEnabled();
  });

  it("issue action confirms before calling the issue endpoint", async () => {
    const approvedPo = mockPurchaseOrder({ status: "approved" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([approvedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(approvedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Mark as locally issued" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Mark this purchase order as internally issued? This will not send it externally.",
    );
    expect(issuePurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("receive action confirms before calling the receive endpoint", async () => {
    const issuedPo = mockPurchaseOrder({ status: "issued" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([issuedPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(issuedPo);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Receive" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Mark this purchase order as received? This will not update stock yet.",
    );
    expect(receivePurchaseOrder).toHaveBeenCalledWith(500);
  });

  it("shows backend errors from approval workflow actions", async () => {
    const pendingPo = mockPurchaseOrder({ status: "pending_approval" });
    vi.mocked(listPurchaseOrders).mockResolvedValue([pendingPo]);
    vi.mocked(getPurchaseOrder).mockResolvedValue(pendingPo);
    vi.mocked(getPurchaseOrderPreflight).mockResolvedValue(
      mockPurchaseOrderPreflight({
        status: "pending_approval",
        can_submit: false,
        can_approve: true,
        overall_status: "ready",
        warnings: [],
        line_checks: [],
        summary_counts: {
          line_count: 1,
          blocker_count: 0,
          warning_count: 0,
          lines_with_blockers: 0,
          lines_with_warnings: 0,
        },
      }),
    );
    vi.mocked(approvePurchaseOrder).mockRejectedValue(
      new Error("Cannot approve a purchase order with no lines."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Purchase Orders" }));
    await screen.findByText("Acme Supplies");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText(
        "Purchase order action failed: Cannot approve a purchase order with no lines.",
      ),
    ).toBeInTheDocument();
  });

  it("recommendations tab renders with the advisory safety message", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(await screen.findByText("No recommendations found.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Manager Review Summary" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Recommendations are advisory. Converting a recommendation only creates a draft purchase order. It does not approve or issue it.",
      ),
    ).toBeInTheDocument();
  });

  it("manager review summary displays counts and guidance", async () => {
    vi.mocked(getRecommendationReviewSummary).mockResolvedValue(
      mockRecommendationReviewSummary({
        total_existing_recommendations: 8,
        pending_review_recommendations: 3,
        accepted_recommendations: 2,
        rejected_recommendations: 1,
        stale_demand_candidates: 4,
        manager_approved_stale_queue_count: 2,
        cleanup_candidates_count: 5,
        recommendations_ready_for_manual_review: 2,
        recommendations_blocked_from_po_conversion: 5,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    const panel = await screen.findByRole("region", { name: "Manager Review Summary" });
    expect(within(panel).getByText("Total recommendations")).toBeInTheDocument();
    expect(within(panel).getByText("8")).toBeInTheDocument();
    expect(within(panel).getByText("Pending review")).toBeInTheDocument();
    expect(within(panel).getByText("3")).toBeInTheDocument();
    expect(within(panel).getByText("Stale-demand candidates")).toBeInTheDocument();
    expect(within(panel).getByText("Manager-approved stale")).toBeInTheDocument();
    expect(within(panel).getByText("Blocked or unsafe")).toBeInTheDocument();
    expect(
      within(panel).getByText("There are cleanup candidates that should be reviewed before PO conversion."),
    ).toBeInTheDocument();
  });

  it("manager review summary export buttons call CSV helpers", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    const panel = await screen.findByRole("region", { name: "Manager Review Summary" });
    await userEvent.click(within(panel).getByRole("button", { name: "Review Summary CSV" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Stale Demand Review CSV" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Manager-Approved Queue CSV" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Cleanup Candidates CSV" }));

    expect(exportRecommendationReviewSummaryCsv).toHaveBeenCalled();
    expect(exportStaleDemandReviewCsv).toHaveBeenCalled();
    expect(exportManagerApprovedStaleQueueCsv).toHaveBeenCalled();
    expect(exportRecommendationCleanupCandidatesCsv).toHaveBeenCalled();
  });

  it("manager review summary failure is non-blocking", async () => {
    vi.mocked(getRecommendationReviewSummary).mockRejectedValue(new Error("Summary offline"));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(
      await screen.findByText("Could not load manager review summary: Summary offline"),
    ).toBeInTheDocument();
    expect(await screen.findByText("No recommendations found.")).toBeInTheDocument();
  });

  it("recommendations tab displays stale-demand review candidates", async () => {
    vi.mocked(getStaleDemandReview).mockResolvedValue(mockStaleDemandReviewWithCandidate());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(await screen.findByRole("heading", { name: "Stale Demand Review" })).toBeInTheDocument();
    expect(screen.getByText("Demand is stale; manager review required before PO.")).toBeInTheDocument();
    expect(screen.getByText("Stale Product")).toBeInTheDocument();
    expect(screen.getByText("3020")).toBeInTheDocument();
    expect(screen.getByText("manual_review")).toBeInTheDocument();
    expect(screen.getByText("unreviewed")).toBeInTheDocument();
    expect(screen.getByLabelText("Decision for Product ID 3020")).toBeInTheDocument();
  });

  it("saving stale-demand decision calls the manager decision endpoint", async () => {
    vi.mocked(getStaleDemandReview).mockResolvedValue(mockStaleDemandReviewWithCandidate());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    await screen.findByRole("heading", { name: "Stale Demand Review" });
    await userEvent.selectOptions(
      screen.getByLabelText("Decision for Product ID 3020"),
      "manager_approved_one_time",
    );
    await userEvent.clear(screen.getByLabelText("Reviewer for Product ID 3020"));
    await userEvent.type(screen.getByLabelText("Reviewer for Product ID 3020"), "Maged");
    await userEvent.type(screen.getByLabelText("Decision notes for Product ID 3020"), "Approved for demo.");
    await userEvent.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() =>
      expect(saveStaleDemandReviewDecision).toHaveBeenCalledWith(3020, {
        decision: "manager_approved_one_time",
        reviewed_by: "Maged",
        notes: "Approved for demo.",
      }),
    );
  });

  it("manager-approved stale queue renders and can create a review recommendation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(getManagerApprovedStaleQueue).mockResolvedValue(mockManagerApprovedStaleQueue());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(await screen.findByRole("heading", { name: "Manager-Approved Stale Queue" })).toBeInTheDocument();
    expect(screen.getByText("ready_for_manual_recommendation")).toBeInTheDocument();
    expect(screen.getByText("Approved for one-time reorder.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create review recommendation" }));

    await waitFor(() =>
      expect(createManagerApprovedStaleReviewRecommendation).toHaveBeenCalledWith(3020),
    );
  });

  it("manager-approved stale queue disables create action when safety blocks remain", async () => {
    vi.mocked(getManagerApprovedStaleQueue).mockResolvedValue(
      mockManagerApprovedStaleQueue({
        summary: {
          decisions_evaluated: 1,
          total_candidates: 1,
          safety_status_counts: { blocked: 1 },
          suggested_next_action_counts: { resolve_hard_blockers: 1 },
          limit: 500,
        },
        items: [
          {
            ...mockManagerApprovedStaleQueue().items[0],
            safety_status: "blocked",
            safety_blockers: ["Missing supplier"],
            suggested_next_action: "resolve_hard_blockers",
          },
        ],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(await screen.findByText("Missing supplier")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create review recommendation" })).toBeDisabled();
  });

  it("recommendation review export buttons call CSV helpers", async () => {
    vi.mocked(getStaleDemandReview).mockResolvedValue(mockStaleDemandReviewWithCandidate());
    vi.mocked(getManagerApprovedStaleQueue).mockResolvedValue(mockManagerApprovedStaleQueue());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    const staleSection = await screen.findByRole("region", { name: "Stale Demand Review" });
    await userEvent.click(within(staleSection).getByRole("button", { name: "Export CSV" }));
    expect(exportStaleDemandReviewCsv).toHaveBeenCalled();

    const queueSection = await screen.findByRole("region", { name: "Manager-Approved Stale Queue" });
    await userEvent.click(within(queueSection).getByRole("button", { name: "Export CSV" }));
    expect(exportManagerApprovedStaleQueueCsv).toHaveBeenCalled();
  });

  it("generate recommendation calls the reorder endpoint", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Generate Reorder Recommendation" }));

    expect(createReorderRecommendation).toHaveBeenCalledWith(1);
    expect(await screen.findByText("Recommendation 900")).toBeInTheDocument();
  });

  it("recommendation list displays status and quantity", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));

    expect(await screen.findByText("Mapped Product")).toBeInTheDocument();
    expect(screen.getByText("pending_review")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("57")).toBeInTheDocument();
    expect(screen.getByText("system")).toBeInTheDocument();
  });

  it("recommendation detail displays supplier and forecast snapshots", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("Recommendation 900")).toBeInTheDocument();
    const detail = screen.getByLabelText("Recommendation details");
    expect(within(detail).getAllByText("Mapped Product").length).toBeGreaterThan(0);
    expect(within(detail).getByText("net_qty")).toBeInTheDocument();
    expect(within(detail).getByText("recent_or_current")).toBeInTheDocument();
    expect(within(detail).getByText("2026-07-01")).toBeInTheDocument();
    expect(within(detail).getByText("18.26")).toBeInTheDocument();
    expect(within(detail).getByText("order_ready")).toBeInTheDocument();
    expect(within(detail).getByText("Ready for PO using current MOQ and pack-size inputs.")).toBeInTheDocument();
    expect(within(detail).getByText("Pack size required")).toBeInTheDocument();
    expect(within(detail).getByText("Cost required")).toBeInTheDocument();
    expect(within(detail).getByText("Stale-demand policy")).toBeInTheDocument();
    expect(within(detail).getByText(/2\s*\(product_record\)/)).toBeInTheDocument();
    expect(within(detail).getByText(/9\.5\s*\(orderpro_product_cost\)/)).toBeInTheDocument();
    expect(within(detail).getByText("missing_pack_size")).toBeInTheDocument();
    expect(within(detail).getAllByText("Stock is below reorder point.").length).toBeGreaterThan(0);
    expect(screen.getByText("ACME-1")).toBeInTheDocument();
    expect(screen.getByText("Acme Product Pack")).toBeInTheDocument();
    expect(screen.getByText("product_supplier")).toBeInTheDocument();
    expect(screen.getByText("order_now")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("PO readiness panel renders ready state with canonical supplier source and warnings", async () => {
    const accepted = mockRecommendation({ status: "accepted" });
    vi.mocked(listRecommendations).mockResolvedValue([accepted]);
    vi.mocked(getRecommendation).mockResolvedValue(accepted);
    vi.mocked(getRecommendationPOReadiness).mockResolvedValue(
      mockRecommendationPOReadiness({
        can_create_draft_po: true,
        warnings: ["Missing pack size; no order multiple is applied unless reviewed"],
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    const panel = await screen.findByRole("region", { name: "PO Readiness" });
    expect(within(panel).getByText("Ready to create draft PO")).toBeInTheDocument();
    expect(within(panel).getByText("products.supplier_id")).toBeInTheDocument();
    expect(within(panel).getByText("ok")).toBeInTheDocument();
    expect(
      within(panel).getByText("Missing pack size; no order multiple is applied unless reviewed"),
    ).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Convert to Draft PO" })).toBeEnabled();
  });

  it("PO readiness panel shows blockers and disables conversion when blocked", async () => {
    const accepted = mockRecommendation({ status: "accepted" });
    vi.mocked(listRecommendations).mockResolvedValue([accepted]);
    vi.mocked(getRecommendation).mockResolvedValue(accepted);
    vi.mocked(getRecommendationPOReadiness).mockResolvedValue(
      mockRecommendationPOReadiness({
        can_create_draft_po: false,
        blockers: ["Product is missing a canonical supplier assignment.", "Product is missing usable supplier lead time."],
        warnings: [],
        canonical_supplier_check_result: "missing",
        supplier_id: null,
        supplier_name: null,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    const panel = await screen.findByRole("region", { name: "PO Readiness" });
    expect(within(panel).getByText("Not ready for draft PO")).toBeInTheDocument();
    expect(within(panel).getByText("This recommendation cannot create a draft PO yet.")).toBeInTheDocument();
    expect(within(panel).getByText("Product is missing a canonical supplier assignment.")).toBeInTheDocument();
    expect(within(panel).getByText("Product is missing usable supplier lead time.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Convert to Draft PO" })).toBeDisabled();
  });

  it("PO readiness endpoint failure shows a non-blocking detail error", async () => {
    const accepted = mockRecommendation({ status: "accepted" });
    vi.mocked(listRecommendations).mockResolvedValue([accepted]);
    vi.mocked(getRecommendation).mockResolvedValue(accepted);
    vi.mocked(getRecommendationPOReadiness).mockRejectedValue(new Error("Readiness offline"));

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    const panel = await screen.findByRole("region", { name: "PO Readiness" });
    expect(within(panel).getByText(/PO readiness unavailable: Readiness offline/)).toBeInTheDocument();
    expect(screen.getByText("Recommendation 900")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Convert to Draft PO" })).toBeEnabled();
  });

  it("generate AI explanation button renders on recommendation detail", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByRole("button", { name: "Generate AI Explanation" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "AI explanations are advisory only. They do not approve, issue, or place purchase orders.",
      ),
    ).toBeInTheDocument();
  });

  it("clicking generate AI explanation calls the correct endpoint", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Generate AI Explanation" }));

    expect(generateRecommendationLLMExplanation).toHaveBeenCalledWith(900);
  });

  it("shows loading state while generating AI explanation", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());
    let resolveExplanation: (value: RecommendationLLMExplanation) => void = () => {};
    vi.mocked(generateRecommendationLLMExplanation).mockReturnValue(
      new Promise((resolve) => {
        resolveExplanation = resolve;
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Generate AI Explanation" }));

    expect(screen.getByRole("button", { name: "Generating AI Explanation..." })).toBeDisabled();
    resolveExplanation(mockLLMExplanation());
  });

  it("displays AI explanation output after generation", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());
    vi.mocked(generateRecommendationLLMExplanation).mockResolvedValue(
      mockLLMExplanation({
        summary: "Reorder is recommended.",
        explanation: "Stock is low and the supplier mapping is confirmed.",
        confidence: 0.72,
      }),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Generate AI Explanation" }));

    expect(await screen.findByText("AI explanation generated.")).toBeInTheDocument();
    expect(screen.getByText("Reorder is recommended.")).toBeInTheDocument();
    expect(screen.getByText("Stock is low and the supplier mapping is confirmed.")).toBeInTheDocument();
    expect(screen.getByText("0.72")).toBeInTheDocument();
    expect(screen.getByText("mock")).toBeInTheDocument();
    expect(screen.getByText("mock-v1")).toBeInTheDocument();
  });

  it("displays backend AI explanation errors clearly", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());
    vi.mocked(generateRecommendationLLMExplanation).mockRejectedValue(
      new Error("OpenAI provider is configured but real LLM calls are disabled."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Generate AI Explanation" }));

    expect(
      await screen.findByText(
        "Recommendation action failed: OpenAI provider is configured but real LLM calls are disabled.",
      ),
    ).toBeInTheDocument();
  });

  it("AI explanation generation does not present recommendation as accepted or approved", async () => {
    const pending = mockRecommendation({ status: "pending_review" });
    vi.mocked(listRecommendations).mockResolvedValue([pending]);
    vi.mocked(getRecommendation).mockResolvedValue(pending);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Generate AI Explanation" }));

    const detail = await screen.findByLabelText("Recommendation details");
    expect(within(detail).getByText("pending_review")).toBeInTheDocument();
    expect(within(detail).queryByText("accepted")).not.toBeInTheDocument();
    expect(within(detail).queryByText("approved")).not.toBeInTheDocument();
  });

  it("accept recommendation calls the accept endpoint", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Accept" }));

    expect(acceptRecommendation).toHaveBeenCalledWith(900, { reviewed_by: "manual" });
  });

  it("reject recommendation confirms before calling reject endpoint", async () => {
    vi.mocked(listRecommendations).mockResolvedValue([mockRecommendation()]);
    vi.mocked(getRecommendation).mockResolvedValue(mockRecommendation());

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.type(await screen.findByLabelText("Reject reason"), "Too early");
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(window.confirm).toHaveBeenCalledWith("Reject this recommendation?");
    expect(rejectRecommendation).toHaveBeenCalledWith(900, {
      rejected_reason: "Too early",
      reviewed_by: "manual",
    });
  });

  it("convert recommendation confirms before calling convert endpoint", async () => {
    const accepted = mockRecommendation({ status: "accepted" });
    vi.mocked(listRecommendations).mockResolvedValue([accepted]);
    vi.mocked(getRecommendation).mockResolvedValue(accepted);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await userEvent.click(await screen.findByRole("button", { name: "Convert to Draft PO" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Convert this recommendation to a draft purchase order? This will not approve or issue it.",
    );
    expect(convertRecommendationToDraftPO).toHaveBeenCalledWith(900);
  });

  it("convert button is hidden for rejected recommendations", async () => {
    const rejected = mockRecommendation({ status: "rejected" });
    vi.mocked(listRecommendations).mockResolvedValue([rejected]);
    vi.mocked(getRecommendation).mockResolvedValue(rejected);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await screen.findByText("Mapped Product");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Recommendation 900");

    expect(screen.queryByRole("button", { name: "Convert to Draft PO" })).not.toBeInTheDocument();
  });

  it("backend recommendation errors display clearly", async () => {
    vi.mocked(createReorderRecommendation).mockRejectedValue(
      new Error("Product does not have a valid ProductSupplier mapping."),
    );

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Recommendations" }));
    await userEvent.type(screen.getByLabelText("Product ID"), "99");
    await userEvent.click(screen.getByRole("button", { name: "Generate Reorder Recommendation" }));

    expect(
      await screen.findByText(
        "Recommendation action failed: Product does not have a valid ProductSupplier mapping.",
      ),
    ).toBeInTheDocument();
  });
});
