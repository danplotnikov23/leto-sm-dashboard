from pydantic import BaseModel, Field


class OzonAccrualArticleSummary(BaseModel):
    offer_id: str
    sku: str | None = None
    title: str | None = None
    sold_quantity: int
    sales_total: float
    revenue: float
    discount_points: float
    partner_programs: float
    ozon_commission: float
    acquiring: float
    ad_charges: float
    returns: float
    delivery_services: float
    other_services: float
    compensations: float
    total: float
    breakdown: dict[str, float] = Field(default_factory=dict)


class OzonAccrualsSummary(BaseModel):
    report_path: str
    row_count: int
    article_count: int
    period: str | None
    totals: dict[str, float]
    accounting_note: str


class OzonAccrualLookupResponse(BaseModel):
    found: bool
    article: OzonAccrualArticleSummary | None = None
    accounting_note: str
