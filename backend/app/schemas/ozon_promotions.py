from pydantic import BaseModel, Field


class OzonPromotionKpi(BaseModel):
    sales_total_revenue_rub: float = 0
    sales_total_qty: int = 0
    promo_revenue_rub: float = 0
    promo_qty: int = 0
    promo_expense_rub: float = 0
    non_promo_revenue_rub: float = 0
    non_promo_qty: int = 0
    promo_drr_percent: float | None = None
    promo_share_percent: float | None = None
    discount_share_percent: float | None = None
    average_promo_discount_percent: float | None = None
    promo_articles_count: int = 0
    missing_unit_articles_count: int = 0
    rows_count: int = 0
    unmatched_promo_rows: int = 0


class OzonPromotionAnalysisRow(BaseModel):
    offer_id: str | None = None
    sku: str | None = None
    title: str | None = None
    promotion_name: str | None = None
    unit_price_with_vat_rub: float | None = None
    sales_total_revenue_rub: float = 0
    sales_total_qty: int = 0
    promo_revenue_rub: float = 0
    promo_qty: int = 0
    promo_expense_rub: float = 0
    discount_per_unit_rub: float | None = None
    discount_percent: float | None = None
    non_promo_revenue_rub: float = 0
    non_promo_qty: int = 0
    promo_drr_percent: float | None = None
    promo_share_percent: float | None = None
    avg_total_price_rub: float | None = None
    avg_promo_price_rub: float | None = None
    match_status: str = "matched"
    source_notes: list[str] = Field(default_factory=list)


class OzonPromotionAnalyzeResponse(BaseModel):
    kpi: OzonPromotionKpi
    rows: list[OzonPromotionAnalysisRow]
    warnings: list[str] = Field(default_factory=list)
    sales_columns: dict[str, str] = Field(default_factory=dict)
    promotion_columns: dict[str, str] = Field(default_factory=dict)
