from pydantic import BaseModel, Field

from app.schemas.unit_economy_index import UnitEconomyProduct


class OzonIntegrationStatus(BaseModel):
    seller_credentials_configured: bool
    performance_credentials_configured: bool


class OzonHealthResponse(BaseModel):
    status: str
    seller: str
    performance: str


class OzonCampaign(BaseModel):
    id: str
    title: str
    state: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class OzonCampaignsResponse(BaseModel):
    campaigns: list[OzonCampaign]


class OzonPromotionInfo(BaseModel):
    action_id: str
    title: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    product_id: str | None = None
    price_with_vat: float | None = None
    action_price_with_vat: float | None = None
    max_action_price_with_vat: float | None = None
    discount_percent: float | None = None


class OzonCampaignProduct(BaseModel):
    campaign_id: str
    performance_object_id: str
    seller_product_id: str | None = None
    sku: str | None = None
    offer_id: str | None = None
    title: str | None = None
    price: str | None = None
    old_price: str | None = None
    primary_image: str | None = None
    vat: str | None = None
    unit_economy_match_key: str | None = None
    unit_economy: UnitEconomyProduct | None = None
    promotions: list[OzonPromotionInfo] = Field(default_factory=list)
    raw: dict[str, object] = Field(default_factory=dict)


class OzonCampaignProductsResponse(BaseModel):
    products: list[OzonCampaignProduct]


class OzonCampaignPerformanceMetrics(BaseModel):
    campaign_id: str
    title: str | None = None
    status: str | None = None
    views: int
    clicks: int
    to_cart: int
    orders: int
    revenue: float
    ad_spend: float
    drr_percent: float | None
    ctr_percent: float | None
    average_cpc: float | None


class OzonCampaignModeledEconomics(BaseModel):
    vat_multiplier: float
    revenue_without_vat: float
    ad_spend_without_vat: float
    average_order_revenue_without_vat: float | None
    average_ad_spend_per_order_without_vat: float | None
    break_even_expense_with_ozon_commission_per_order: float | None
    unit_expense_with_ozon_commission_min: float | None
    unit_expense_with_ozon_commission_max: float | None
    unit_expense_with_ozon_commission_avg: float | None
    profit_before_tax_min: float | None
    profit_before_tax_max: float | None
    net_profit_min: float | None
    net_profit_max: float | None
    exact_profit_available: bool
    note: str


class OzonSkuProfitBreakdown(BaseModel):
    revenue_without_vat: float
    ad_spend_without_vat: float
    revenue_without_vat_per_order: float | None = None
    ad_spend_without_vat_per_order: float | None = None
    unit_expense_per_order: float | None
    orders: int
    unit_expense_total: float | None
    profit_before_tax: float | None
    profit_before_tax_per_order: float | None = None
    tax_rate: float
    tax_amount: float | None
    tax_amount_per_order: float | None = None
    net_profit: float | None
    net_profit_per_order: float | None = None
    unit_economy_price_without_vat: float | None = None
    unit_economy_profit_before_tax: float | None = None
    unit_economy_net_profit: float | None = None
    profit_before_tax_formula: str
    profit_before_tax_per_order_formula: str = "Нет детализации на 1 заказ"
    net_profit_formula: str
    net_profit_per_order_formula: str = "Нет детализации чистой прибыли на 1 заказ"


class OzonSkuEfficiencyRow(BaseModel):
    campaign_id: str
    campaign_ids: list[str] = Field(default_factory=list)
    campaign_titles: list[str] = Field(default_factory=list)
    sku: str
    offer_id: str | None
    title: str | None
    views: int
    clicks: int
    to_cart: int
    orders: int
    direct_orders: int = 0
    sku_orders: int = 0
    revenue_with_vat: float
    revenue_without_vat: float
    direct_revenue_with_vat: float = 0
    direct_revenue_without_vat: float = 0
    sku_revenue_with_vat: float = 0
    sku_revenue_without_vat: float = 0
    model_revenue_without_vat: float = 0
    ad_spend_with_vat: float
    ad_spend_without_vat: float
    sku_ad_spend_without_vat: float = 0
    model_attribution_included_in_sku: bool = False
    drr_percent: float | None
    ctr_percent: float | None
    average_cpc: float | None
    model_orders: int
    model_revenue_with_vat: float
    total_ordered_amount_with_vat: float
    unit_expense_with_ozon_commission: float | None
    unit_economy_price_with_vat: float | None = None
    unit_economy_price_without_vat: float | None = None
    average_ad_order_revenue_with_vat: float | None = None
    average_ad_order_revenue_without_vat: float | None = None
    ad_price_discount_percent: float | None = None
    promotion_matched: bool = False
    promotion_count: int = 0
    promotion_action_ids: list[str] = Field(default_factory=list)
    promotion_titles: list[str] = Field(default_factory=list)
    promotion_price_with_vat: float | None = None
    promotion_discount_percent: float | None = None
    profit_before_tax: float | None
    net_profit: float | None
    profit_breakdown: OzonSkuProfitBreakdown | None = None
    matched_unit_economy: bool
    total_sales_orders: int | None = None
    total_sales_revenue_with_vat: float | None = None
    total_sales_revenue_without_vat: float | None = None
    total_sales_drr_percent: float | None = None
    average_total_order_revenue_without_vat: float | None = None
    total_price_discount_percent: float | None = None
    organic_orders: int | None = None
    organic_revenue_without_vat: float | None = None
    average_organic_order_revenue_without_vat: float | None = None
    organic_price_discount_percent: float | None = None
    organic_unit_expense_total: float | None = None
    organic_profit_before_tax: float | None = None
    organic_net_profit: float | None = None
    all_sales_profit_before_tax: float | None = None
    all_sales_net_profit: float | None = None
    total_sales_matched: bool = False


class OzonSkuEfficiencySegment(BaseModel):
    date_from: str
    date_to: str
    report_uuid: str
    report_state: str
    unit_economy_version: str | None = None
    unit_economy_version_valid_from: str | None = None
    unit_economy_workbook_path: str | None = None
    rows: list[OzonSkuEfficiencyRow]
    total: OzonSkuEfficiencyRow | None


class OzonSkuEfficiencyResponse(BaseModel):
    campaign_id: str
    date_from: str
    date_to: str
    rows: list[OzonSkuEfficiencyRow]
    total: OzonSkuEfficiencyRow | None
    adjustment_ad_spend_with_vat: float
    adjustment_ad_spend_without_vat: float
    report_uuid: str
    report_state: str
    unit_economy_version: str | None = None
    unit_economy_version_valid_from: str | None = None
    unit_economy_workbook_path: str | None = None
    unit_economy_warning: str | None = None
    is_composite: bool = False
    segments: list[OzonSkuEfficiencySegment] = Field(default_factory=list)
    total_sales_report_state: str | None = None
    total_sales_warning: str | None = None
    promotion_report_state: str | None = None
    promotion_warning: str | None = None


class OzonSalesAnalyticsRow(BaseModel):
    sku: str
    offer_id: str | None
    title: str | None
    total_orders: int
    total_revenue_with_vat: float
    total_revenue_without_vat: float
    ad_orders: int
    ad_revenue_without_vat: float
    model_orders: int
    model_revenue_without_vat: float
    ad_spend_without_vat: float
    organic_orders: int
    organic_revenue_without_vat: float
    unit_expense_with_ozon_commission: float | None
    profit_before_tax: float | None
    net_profit: float | None
    drr_percent: float | None
    unit_economy_price_without_vat: float | None = None
    average_total_order_revenue_without_vat: float | None = None
    total_price_discount_percent: float | None = None
    average_organic_order_revenue_without_vat: float | None = None
    organic_price_discount_percent: float | None = None
    promotion_matched: bool = False
    promotion_count: int = 0
    promotion_action_ids: list[str] = Field(default_factory=list)
    promotion_titles: list[str] = Field(default_factory=list)
    promotion_price_with_vat: float | None = None
    promotion_discount_percent: float | None = None
    matched_unit_economy: bool
    has_ad_spend: bool
    has_sales: bool


class OzonSalesAnalyticsResponse(BaseModel):
    date_from: str
    date_to: str
    rows: list[OzonSalesAnalyticsRow]
    total: OzonSalesAnalyticsRow
    unit_economy_version: str | None = None
    unit_economy_version_valid_from: str | None = None
    unit_economy_workbook_path: str | None = None
    warning: str | None = None


class OzonSkuDailyProfitRow(BaseModel):
    date: str
    sku: str
    offer_id: str | None
    title: str | None
    ordered_amount_with_vat: float
    ordered_units: int
    average_unit_price_with_vat: float | None
    average_unit_price_without_vat: float | None
    unit_economy_version_valid_from: str | None
    unit_economy_sheet_name: str | None
    unit_expense_with_ozon_commission: float | None
    profit_before_tax_per_unit: float | None
    profit_tax_per_unit: float | None
    net_profit_per_unit: float | None
    net_profit_before_ads: float | None
    allocated_ad_spend_without_vat: float
    net_profit_after_ads: float | None
    matched_unit_economy: bool


class OzonSkuDailyProfitTotal(BaseModel):
    ordered_amount_with_vat: float
    ordered_amount_without_vat: float
    ordered_units: int
    net_profit_before_ads: float | None
    ad_spend_without_vat: float
    net_profit_after_ads: float | None
    matched_unit_economy: bool


class OzonSkuDailyProfitResponse(BaseModel):
    date_from: str
    date_to: str
    sku: str
    offer_id: str | None
    title: str | None
    vat_multiplier: float
    profit_tax_rate: float
    rows: list[OzonSkuDailyProfitRow]
    total: OzonSkuDailyProfitTotal


class OzonSalesForecastItem(BaseModel):
    sku: str | None = None
    offer_id: str | None = None
    target_ad_spend_with_vat: float = Field(gt=0)
    target_drr_percent: float = Field(gt=0)


class OzonSalesForecastRequest(BaseModel):
    date_from: str
    date_to: str
    target_ad_spend_with_vat: float | None = Field(default=None, gt=0)
    target_drr_percent: float | None = Field(default=None, gt=0)
    items: list[OzonSalesForecastItem] = Field(default_factory=list)


class OzonSalesForecastRow(BaseModel):
    sku: str
    offer_id: str | None
    title: str | None
    target_ad_spend_with_vat: float
    target_drr_percent: float | None
    ad_spend_share_percent: float
    fact_total_orders: int
    fact_total_revenue_without_vat: float
    fact_ad_spend_without_vat: float
    fact_ad_revenue_without_vat: float
    fact_organic_orders: int
    fact_organic_revenue_without_vat: float
    forecast_ad_spend_without_vat: float
    forecast_ad_revenue_without_vat: float
    forecast_ad_orders: float
    forecast_organic_orders: int
    forecast_organic_revenue_without_vat: float
    forecast_total_orders: float
    forecast_total_revenue_without_vat: float
    unit_expense_with_ozon_commission: float | None
    forecast_ad_profit_before_tax: float | None
    forecast_ad_net_profit: float | None
    forecast_organic_profit_before_tax: float | None
    forecast_organic_net_profit: float | None
    forecast_total_profit_before_tax: float | None
    forecast_total_net_profit: float | None
    matched_unit_economy: bool


class OzonSalesForecastResponse(BaseModel):
    date_from: str
    date_to: str
    target_ad_spend_with_vat: float
    target_ad_spend_without_vat: float
    target_drr_percent: float
    target_ad_revenue_without_vat: float
    rows: list[OzonSalesForecastRow]
    total: OzonSalesForecastRow
    unit_economy_version: str | None = None
    unit_economy_version_valid_from: str | None = None
    unit_economy_workbook_path: str | None = None
    warning: str | None = None


class OzonStatisticsReportStatus(BaseModel):
    campaign_id: str
    report_uuid: str
    state: str
    link: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class OzonStoredReportSummary(BaseModel):
    campaign_id: str
    date_from: str
    date_to: str
    report_uuid: str
    state: str
    rows_count: int
    total_ad_spend_without_vat: float | None = None
    total_net_profit: float | None = None
    unit_economy_version: str | None = None
    updated_at: str


class OzonStoredReportsResponse(BaseModel):
    reports: list[OzonStoredReportSummary]


class OzonReportJobCreateRequest(BaseModel):
    campaign_id: str
    date_from: str
    date_to: str


class OzonReportJobResponse(BaseModel):
    job_id: str
    campaign_id: str
    date_from: str
    date_to: str
    status: str
    phase: str
    progress_percent: int
    message: str
    result_ready: bool
    result_source: str | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class OzonCampaignEfficiencyResponse(BaseModel):
    date_from: str
    date_to: str
    metrics: OzonCampaignPerformanceMetrics
    modeled_economics: OzonCampaignModeledEconomics
    products: list[OzonCampaignProduct]
    matched_products: int
    can_calculate_sku_profit: bool
    profit_calculation_status: str
