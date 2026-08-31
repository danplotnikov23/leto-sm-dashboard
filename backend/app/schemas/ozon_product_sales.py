from pydantic import BaseModel, Field


class OzonProductSalesRow(BaseModel):
    sku: str
    offer_id: str | None = None
    title: str | None = None
    ordered_units: int
    redeemed_units: int
    cancelled_units: int
    revenue_with_vat: float
    revenue_without_vat: float
    unit_expense_with_ozon_commission: float | None = None
    profit_before_ads: float | None = None
    matched_unit_economy: bool


class OzonProductSalesTotal(BaseModel):
    ordered_units: int
    redeemed_units: int
    cancelled_units: int
    revenue_with_vat: float
    revenue_without_vat: float
    profit_before_ads: float | None = None
    ad_spend_without_vat: float | None = None
    net_profit: float | None = None
    drr_percent: float | None = None


class OzonProductSalesResponse(BaseModel):
    date_from: str
    date_to: str
    rows: list[OzonProductSalesRow]
    total: OzonProductSalesTotal
    unit_economy_version: str | None = None
    unit_economy_warning: str | None = None
    ad_spend_matched: bool = False
    warning: str | None = None
    errors: list[str] = Field(default_factory=list)


class OzonProductSalesImportSummary(BaseModel):
    id: int
    date_from: str
    date_to: str
    source_filename: str
    sku_count: int
    row_count: int
    has_daily_breakdown: bool
    created_at: str


class OzonProductSalesImportsResponse(BaseModel):
    imports: list[OzonProductSalesImportSummary]
