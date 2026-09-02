from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, PositiveFloat

from app.domain.models import (
    CompetitorImportResult,
    CompetitorOffer,
    DashboardKpi,
    ProductAnalysis,
    ShortlistItem,
)
from app.services.ozon_client import OzonIntegrationStatus, OzonPerformanceTokenCheck
from app.services.ozon_seller_analytics import (
    OzonBestsellersImportRequest,
    OzonBestsellersRequest,
    OzonSellerAnalyticsAccessCheck,
    OzonSellerAnalyticsStatus,
)


class AnalyzeRequest(BaseModel):
    sale_price_vat_included: float | None = None
    package_cost: float = 25.0
    fulfillment_processing_cost: float = 45.0
    advertising_drr_percent: float = 12.0
    ozon_visible_discount_percent: float = Field(
        default=30.0,
        description="Видимая скидка от цены до скидки до текущей цены Ozon.",
    )
    bank_card_discount_percent: float = Field(
        default=8.0,
        description=(
            "Сценарная скидка цены с картой/банком. Не считается расходом без подтверждения."
        ),
    )
    discount_percent: float = 0.0
    seller_bonus_percent: float = Field(
        default=45.0,
        description="Оценка начисления Ozon баллами за скидки, в процентах от цены.",
    )
    partner_program_percent: float = Field(
        default=0.5,
        description="Оценка начисления по программам партнеров, в процентах от цены.",
    )
    delivery_accrual_percent: float = Field(
        default=0.0,
        description="Оценка положительного начисления за доставку/логистику, если оно есть.",
    )
    tax_regime: Literal["ip_usn_6", "osno"] = Field(
        default="ip_usn_6",
        description="Налоговый сценарий: ip_usn_6 или osno.",
    )
    use_vat: bool = Field(default=False, description="Учитывать НДС в выручке/закупке.")
    usn_tax_rate: float = Field(default=0.06, description="УСН Доходы для ИП.")
    usn_additional_contribution_rate: float = Field(
        default=0.01,
        description="Дополнительный взнос ИП 1% с дохода свыше 300 000 ₽.",
    )
    fast_payout_fee_percent: float = Field(
        default=2.45,
        description="Быстрый вывод средств Ozon, процент от начислений всего.",
    )
    designer_content_percent: float = Field(
        default=4.0,
        description="Дизайнер/контент, процент от начислений всего.",
    )
    business_fulfillment_pickup_percent: float = Field(
        default=0.0,
        description="Фулфилмент и забор товара, процент от начислений всего.",
    )


class DashboardResponse(BaseModel):
    kpi: DashboardKpi
    rows: list[ProductAnalysis]


class ShortlistResponse(BaseModel):
    items: list[ShortlistItem]


class ShortlistStockRefreshResponse(BaseModel):
    matched: int
    updated: int
    unmatched: int
    items: list[ShortlistItem]


class ShortlistUpdateRequest(BaseModel):
    supplier_name: str | None = None
    supplier_article: str | None = None
    product_title: str | None = None
    group_name: str | None = None
    subgroup_name: str | None = None
    offer_quantity: int | None = Field(default=None, ge=1)
    purchase_price_vat_included: PositiveFloat | None = None
    sale_price_vat_included: PositiveFloat | None = None
    length_cm: float | None = Field(default=None, gt=0)
    width_cm: float | None = Field(default=None, gt=0)
    height_cm: float | None = Field(default=None, gt=0)
    seller_bonus_percent: float | None = Field(default=None, ge=0)
    advertising_drr_percent: float | None = Field(default=None, ge=0)
    package_cost: float | None = Field(default=None, ge=0)
    fulfillment_processing_cost: float | None = Field(default=None, ge=0)
    planned_sales_qty: int | None = Field(default=None, ge=0)
    sold_qty: int | None = Field(default=None, ge=0)
    note: str | None = None


class CompetitorImportResponse(BaseModel):
    result: CompetitorImportResult
    kpi: DashboardKpi
    rows: list[ProductAnalysis]


class CompetitorOffersImportRequest(BaseModel):
    filename: str = "Ozon Seller visible table"
    offers: list[CompetitorOffer]


class CompetitorOverrideRequest(BaseModel):
    price_vat_included: PositiveFloat = Field(
        description="Цена конкурента на Ozon с НДС/для покупателя."
    )
    url: HttpUrl = Field(description="Реальная ссылка на карточку или страницу конкурента.")
    title: str | None = Field(
        default=None,
        description="Название конкурента, если отличается от нашего товара.",
    )
    match_type: Literal["exact", "analog", "reference"] = Field(
        default="analog",
        description="exact — тот же товар, analog — аналог, reference — ценовой ориентир.",
    )


class OzonStatusResponse(BaseModel):
    integration: OzonIntegrationStatus


class OzonCategoryTreeCheckResponse(BaseModel):
    ok: bool
    source: str = "api"
    categories_count: int
    message: str


class OzonProductListItem(BaseModel):
    product_id: int | str | None = None
    offer_id: str | None = None


class OzonProductListResponse(BaseModel):
    ok: bool
    source: str = "api"
    total_returned: int
    last_id: str | None
    items: list[OzonProductListItem]


class OzonPerformanceStatusResponse(BaseModel):
    integration: OzonIntegrationStatus


class OzonPerformanceTokenCheckResponse(BaseModel):
    result: OzonPerformanceTokenCheck


class OzonSellerAnalyticsStatusResponse(BaseModel):
    integration: OzonSellerAnalyticsStatus


class OzonSellerAnalyticsAccessCheckResponse(BaseModel):
    result: OzonSellerAnalyticsAccessCheck


class OzonSellerAnalyticsPlanResponse(BaseModel):
    source: str = "ozon_seller_web"
    mode: str = "experimental"
    request: OzonBestsellersRequest
    json_endpoint: str
    json_payload: dict[str, object]
    report_endpoint: str
    report_payload: dict[str, object]
    warning: str


class OzonSellerAnalyticsImportResponse(BaseModel):
    result: CompetitorImportResult
    kpi: DashboardKpi
    rows: list[ProductAnalysis]
    searches: list[str]
    offers_loaded: int
    request: OzonBestsellersImportRequest
