from pydantic import BaseModel, Field


class OzonAdAttributionChild(BaseModel):
    sale_type: str
    promoted_sku: str
    purchased_sku: str
    instrument: str | None = None
    placement: str | None = None
    offer_id: str | None = None
    title: str | None = None
    quantity: int
    revenue_with_vat: float
    revenue_without_vat: float
    average_price_without_vat: float | None = None
    unit_cost: float | None = None
    total_cost: float | None = None
    tax: float | None = None
    profit_before_ads: float | None = None
    mapping_source: str
    status: str


class OzonAdAttributionMetrics(BaseModel):
    orders: int
    revenue_with_vat: float
    revenue_without_vat: float
    spend_without_vat: float
    total_cost: float | None = None
    tax: float | None = None
    profit_before_ads: float | None = None
    net_profit: float | None = None
    drr_percent: float | None = None
    romi_percent: float | None = None
    cost_per_order: float | None = None
    coverage_percent: float
    coverage_orders_percent: float
    complete: bool


class OzonAdAttributionRow(BaseModel):
    row_key: str
    promoted_sku: str
    offer_id: str | None = None
    title: str | None = None
    campaign_ids: list[str] = Field(default_factory=list)
    campaign_titles: list[str] = Field(default_factory=list)
    spend_without_vat: float
    direct: OzonAdAttributionMetrics
    with_models: OzonAdAttributionMetrics
    children: list[OzonAdAttributionChild] = Field(default_factory=list)
    status: str
    issues: list[str] = Field(default_factory=list)


class OzonAdAttributionResponse(BaseModel):
    campaign_id: str
    date_from: str
    date_to: str
    report_state: str
    source: str
    unit_economy_version: str | None = None
    unit_economy_warning: str | None = None
    campaign_count: int
    rows: list[OzonAdAttributionRow]
    direct_total: OzonAdAttributionMetrics
    with_models_total: OzonAdAttributionMetrics
    errors: list[str] = Field(default_factory=list)


class OzonPromotionAnalyticsImportSummary(BaseModel):
    id: int
    campaign_id: str
    date_from: str
    date_to: str
    source_filename: str
    created_at: str


class OzonPromotionAnalyticsImportsResponse(BaseModel):
    imports: list[OzonPromotionAnalyticsImportSummary]
