export type Recommendation =
  | "Заводить"
  | "Заводить осторожно"
  | "Только при повышении цены"
  | "Только без акции"
  | "Не заводить"
  | "Нужна ручная проверка";

export interface SupplierProduct {
  id: string;
  supplier_name: string;
  supplier_article: string;
  title: string;
  category: string | null;
  purchase_price_vat_included: number;
  package: string | null;
  multiplicity: number | null;
  weight_kg: number | null;
  dimensions: {
    length_cm: number | null;
    width_cm: number | null;
    height_cm: number | null;
    volume_liters: number | null;
  };
  brand: string | null;
  barcode: string | null;
  stock: number | null;
  status: string;
  source_import_filename: string | null;
  source_imported_at: string | null;
}

export interface ImportIssue {
  row_number: number | null;
  field: string | null;
  message: string;
  severity: "warning" | "error";
}

export interface ImportFieldCoverage {
  field: string;
  label: string;
  source_column: string | null;
  present_rows: number;
  missing_rows: number;
  coverage_percent: number;
}

export interface PriceImportVersion {
  id: string;
  filename: string;
  supplier_name: string;
  imported_at: string;
  total_rows: number;
  accepted_rows: number;
  section_rows: number;
  rejected_rows: number;
  warning_count: number;
  error_count: number;
  source_columns: string[];
  detected_columns: Record<string, string>;
  field_coverage: ImportFieldCoverage[];
  products: SupplierProduct[];
  issues: ImportIssue[];
}

export interface CompetitorImportResult {
  filename: string;
  imported_rows: number;
  matched_products: number;
  skipped_rows: number;
  source: string;
  issues: ImportIssue[];
}

export interface EconomicsBreakdown {
  product_id: string;
  source: string;
  tax_regime: string;
  vat_applicable: boolean;
  vat_rate: number;
  tax_income_basis: number;
  tax_only_break_even_price_vat_included: number;
  list_price_vat_included: number;
  ozon_price_before_discount_vat_included: number;
  ozon_visible_discount_percent: number;
  real_fbs_price_vat_included: number;
  bank_card_price_vat_included: number;
  bank_card_discount_percent: number;
  ozon_min_price_vat_included: number;
  customer_price_after_discount: number;
  effective_customer_price_after_bonus: number;
  buyer_payment_price_vat_included: number;
  ozon_bonus_accrual: number;
  partner_program_accrual: number;
  delivery_accrual: number;
  marketplace_gross_accrual_vat_included: number;
  ozon_services_total: number;
  expected_payout_after_ozon_services: number;
  estimated_competitor_price_vat_included: number | null;
  sale_price_vat_included: number;
  sale_price_vat_excluded: number;
  purchase_price_vat_included: number;
  purchase_price_vat_excluded: number;
  ozon_commission_percent: number;
  commission_source_label: string;
  matched_ozon_category: string | null;
  matched_ozon_product_type: string | null;
  ozon_commission: number;
  logistics: number;
  acquiring: number;
  package_cost: number;
  fulfillment_processing_cost: number;
  storage: number;
  advertising: number;
  advertising_drr_percent: number;
  discount: number;
  seller_bonus_points: number;
  seller_bonus_percent: number;
  seller_bonus_max_spend_percent: number;
  other_costs: number;
  profit_before_tax: number;
  usn_tax: number;
  usn_additional_contribution: number;
  profit_tax: number;
  net_profit: number;
  fast_payout_fee_percent: number;
  fast_payout_fee: number;
  designer_content_percent: number;
  designer_content_cost: number;
  business_fulfillment_pickup_percent: number;
  business_fulfillment_pickup_cost: number;
  business_extra_costs_total: number;
  business_net_profit: number;
  business_margin_percent: number;
  target_margin_percent: number;
  target_business_profit: number;
  max_purchase_price_break_even_vat_included: number;
  supplier_discount_break_even_feasible: boolean;
  required_supplier_discount_break_even_amount: number;
  required_supplier_discount_break_even_percent: number;
  target_purchase_price_vat_included: number;
  supplier_discount_target_feasible: boolean;
  required_supplier_discount_target_amount: number;
  required_supplier_discount_target_percent: number;
  expense_shares_percent: Record<string, number>;
  margin_percent: number;
  markup_percent: number;
  cost_basis_without_commission: number;
  cost_basis_with_commission: number;
  total_expenses_before_tax: number;
  break_even_price_vat_included: number;
  recommended_price_vat_included: number;
  competitiveness_gap: number | null;
  recommendation: Recommendation;
  drr_scenarios: DrrScenario[];
  fbs_batch_scenarios: FbsBatchScenario[];
  warnings: string[];
  formula: string[];
}

export interface DrrScenario {
  drr_percent: number;
  advertising: number;
  profit_before_tax: number;
  profit_tax: number;
  net_profit: number;
  margin_percent: number;
  break_even_price_vat_included: number;
  recommendation: Recommendation;
}

export interface FbsBatchScenario {
  orders_per_day: number;
  supplier_pickup_daily_cost: number;
  ozon_sc_delivery_daily_cost: number;
  fixed_costs_total: number;
  allocated_fixed_cost_per_order: number;
  business_net_profit_after_fixed: number;
  margin_percent: number;
  recommendation: Recommendation;
}

export interface CompetitorSnapshot {
  product_id: string;
  offers: CompetitorOffer[];
  min_price: number | null;
  leader_url: string | null;
  source: string;
}

export interface CompetitorOffer {
  sku: string | null;
  title: string;
  price_vat_included: number;
  url: string | null;
  match_type: "exact" | "analog" | "reference";
  orders_count: number | null;
  avg_purchase_price: number | null;
  buyout_rate: number | null;
  is_promo: boolean;
  source: string;
}

export interface ProductAnalysis {
  product: SupplierProduct;
  economics: EconomicsBreakdown;
  competitor: CompetitorSnapshot;
  readiness: LaunchReadiness;
}

export interface LaunchReadiness {
  status: "Готов к запуску" | "Нужны данные" | "Стоп";
  checks: Record<string, boolean>;
  missing_fields: string[];
  reasons: string[];
}

export interface ShortlistEntry {
  supplier_name: string;
  supplier_article: string;
  product_id: string;
  product_snapshot: SupplierProduct | null;
  source_import_filename: string | null;
  source_imported_at: string | null;
  group_name: string;
  subgroup_name: string;
  offer_quantity: number;
  purchase_price_vat_included: number | null;
  sale_price_vat_included: number | null;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  seller_bonus_percent: number | null;
  advertising_drr_percent: number | null;
  package_cost: number | null;
  fulfillment_processing_cost: number | null;
  planned_sales_qty: number;
  sold_qty: number;
  note: string;
}

export interface ShortlistItem {
  entry: ShortlistEntry;
  analysis: ProductAnalysis;
}

export interface ShortlistResponse {
  items: ShortlistItem[];
}

export interface ShortlistStockRefreshResponse extends ShortlistResponse {
  matched: number;
  updated: number;
  unmatched: number;
}

export interface ShortlistUpdatePayload {
  supplier_name?: string;
  supplier_article?: string;
  product_title?: string;
  group_name?: string;
  subgroup_name?: string;
  offer_quantity?: number;
  purchase_price_vat_included?: number;
  sale_price_vat_included?: number;
  length_cm?: number;
  width_cm?: number;
  height_cm?: number;
  seller_bonus_percent?: number;
  advertising_drr_percent?: number;
  package_cost?: number;
  fulfillment_processing_cost?: number;
  planned_sales_qty?: number;
  sold_qty?: number;
  note?: string;
}

export interface DashboardKpi {
  total_products: number;
  profitable_products: number;
  unprofitable_products: number;
  average_margin_percent: number;
  potential_profit: number;
  high_risk_products: number;
  competitor_below_break_even: number;
}

export interface DashboardResponse {
  kpi: DashboardKpi;
  rows: ProductAnalysis[];
}

export interface CompetitorImportResponse {
  result: CompetitorImportResult;
  kpi: DashboardKpi;
  rows: ProductAnalysis[];
}

export interface OzonIntegrationStatus {
  configured: boolean;
  base_url: string;
  client_id_masked: string | null;
  account_label: string;
  target_store_name: string;
  usage_mode: string;
  data_scope_warning: string;
  message: string;
}

export interface OzonStatusResponse {
  integration: OzonIntegrationStatus;
}

export interface OzonCategoryTreeCheckResponse {
  ok: boolean;
  source: string;
  categories_count: number;
  message: string;
}

export interface OzonProductListResponse {
  ok: boolean;
  source: string;
  total_returned: number;
  last_id: string | null;
  items: Array<{ product_id: number | string | null; offer_id: string | null }>;
}

export interface OzonPerformanceTokenCheckResponse {
  result: {
    ok: boolean;
    expires_in_seconds: number | null;
    token_type: string | null;
    message: string;
  };
}

export interface OzonSellerAnalyticsStatus {
  configured: boolean;
  source: string;
  stability: string;
  base_url: string;
  cookie_configured: boolean;
  cookie_masked: string | null;
  report_workflow: string[];
  json_data_endpoint: string;
  message: string;
  warning: string;
}

export interface OzonSellerAnalyticsStatusResponse {
  integration: OzonSellerAnalyticsStatus;
}

export interface OzonSellerAnalyticsAccessCheckResponse {
  result: {
    ok: boolean;
    configured: boolean;
    source: string;
    status_code: number | null;
    offers_seen: number;
    message: string;
    warning: string;
  };
}

export interface OzonBestsellersRequest {
  search: string | null;
  categories: string[];
  period: "weekly" | "monthly";
  stock: "any_stock" | "with_stock" | "without_stock";
  limit: number;
  offset: number;
  sort_key: string;
}

export interface OzonSellerAnalyticsPlanResponse {
  source: string;
  mode: string;
  request: OzonBestsellersRequest;
  json_endpoint: string;
  json_payload: Record<string, unknown>;
  report_endpoint: string;
  report_payload: Record<string, unknown>;
  warning: string;
}

export interface OzonSellerAnalyticsImportResponse {
  result: CompetitorImportResult;
  kpi: DashboardKpi;
  rows: ProductAnalysis[];
  searches: string[];
  offers_loaded: number;
  request: {
    searches: string[];
    period: "weekly" | "monthly";
    stock: "any_stock" | "with_stock" | "without_stock";
    limit_per_search: number;
    max_pages_per_search: number;
    sort_key: string;
  };
}

// --- Остатки: сверка Ozon vs поставщик (см. app/domain/stock.py) ---

export type StockStatus = "ok" | "critical" | "low" | "mismatch" | "restock" | "unknown";

export interface StockRow {
  offer_id: string;
  name: string;
  ozon_stock: number;
  supplier_stock: number | null;
  supplier_found: boolean;
  status: StockStatus;
}

export interface StockCounts {
  ok: number;
  critical: number;
  low: number;
  mismatch: number;
  restock: number;
  unknown: number;
}

export interface StockSnapshot {
  checked_at: string | null;
  total: number;
  counts: StockCounts;
  diff_count: number;
  rows: StockRow[];
}

export interface StockApplyResult {
  updated: number;
  ok: boolean;
  message: string;
}

// --- Ozon Orders (главный дашборд) ---

export interface OzonOrdersDaily {
  date: string;
  orders: number;
  revenue: number;
  qty: number;
}

export interface OzonOrdersResponse {
  ok: boolean;
  period_days: number;
  total_orders: number;
  total_revenue: number;
  total_qty: number;
  daily: OzonOrdersDaily[];
}

// --- Живая Юнитка (см. app/domain/unitka.py) ---

export interface UnitkaRow {
  id: string;
  row_number: number | null;
  supplier_article: string;
  fulfillment_scheme: string | null;
  ozon_listing: string | null;
  stock: number | null;
  ozon_sku_id: string | null;
  title: string;
  product_type: string | null;
  status: string | null;
  ozon_visibility: string | null;
  in_stock_ozon: number | null;
  in_stock_own: number | null;
  volume_liters_manual: number | null;
  weight_kg: number | null;
  dimensions_mm: string | null;
  tn_ved: string | null;
  honest_mark_required: string | null;
  coinvest_percent: number;
  markup_multiplier: number;
  purchase_price_vat_included: number;
  ozon_commission_percent: number;
  integration_fee: number;
  competitor_price_idd: number | null;
  competitor_price_ozon: number | null;
  url_idd: string | null;
  url_tdcsm: string | null;
  url_competitor: string | null;
}

export interface UnitkaRowComputed {
  price_before_discount_vat_included: number;
  price_with_discount_vat_included: number;
  ozon_points_discount: number;
  customer_price: number;
  sorting_delivery_cost: number;
  fbs_costs: number;
  fulfillment_cost: number;
  designer_salary_cost: number;
  fast_payout_cost: number;
  ozon_commission_amount: number;
  advertising_cost: number;
  acquiring_cost: number;
  other_costs: number;
  tax_amount: number;
  net_profit: number;
  profitability_percent: number;
  idd_price_gap: number | null;
  cost_basis: number;
  cost_basis_with_advertising: number;
  cost_basis_with_advertising_and_commission: number;
  volume_liters_computed: number | null;
  ozon_volume_logistics_reference: number | null;
  fulfillment_office_cost: number;
}

export interface UnitkaItem {
  row: UnitkaRow;
  computed: UnitkaRowComputed;
}

export interface UnitkaImportResult {
  imported: number;
  updated: number;
  skipped: number;
  warnings: string[];
}

export interface UnitkaAssumptions {
  sorting_delivery_rate: number;
  designer_salary_rate: number;
  fast_payout_rate: number;
  advertising_rate: number;
  acquiring_rate: number;
  other_costs_rate: number;
  tax_rate: number;
  fulfillment_office_rate_per_kg: number;
}

export interface PurchasePriceRow {
  offer_id: string;
  supplier_name: string | null;
  unitka_row_id: string | null;
  unitka_title: string | null;
  current_purchase_price: number | null;
  supplier_purchase_price: number | null;
  delta: number | null;
  supplier_found: boolean;
  in_unitka: boolean;
}

export interface PurchasePriceSnapshot {
  checked_at: string;
  total_published: number;
  matched_to_unitka: number;
  supplier_not_found: number;
  diff_count: number;
  rows: PurchasePriceRow[];
}

export interface PurchasePriceApplyResult {
  updated: number;
  ok: boolean;
  message: string;
}
