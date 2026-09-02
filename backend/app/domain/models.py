from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class DataSource(StrEnum):
    API = "api"
    EXCEL = "excel"
    MANUAL = "manual"
    ESTIMATE = "estimate"
    MISSING = "missing"


class RecommendationStatus(StrEnum):
    LIST = "Заводить"
    LIST_CAREFULLY = "Заводить осторожно"
    PRICE_UP_ONLY = "Только при повышении цены"
    NO_PROMO_ONLY = "Только без акции"
    DO_NOT_LIST = "Не заводить"
    MANUAL_REVIEW = "Нужна ручная проверка"


class ProductStatus(StrEnum):
    NEW = "новый"
    FIT = "подходит"
    RISK = "риск"
    UNPROFITABLE = "невыгоден"


class LaunchReadinessStatus(StrEnum):
    READY = "Готов к запуску"
    NEEDS_DATA = "Нужны данные"
    STOP = "Стоп"


class Money(BaseModel):
    amount: float = 0.0
    currency: Literal["RUB"] = "RUB"


class Dimensions(BaseModel):
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None

    @computed_field
    @property
    def volume_liters(self) -> float | None:
        if self.length_cm is None or self.width_cm is None or self.height_cm is None:
            return None
        return round(self.length_cm * self.width_cm * self.height_cm / 1000, 4)


class SupplierProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    supplier_name: str = "Не указан"
    supplier_article: str
    title: str
    category: str | None = None
    purchase_price_vat_included: float
    package: str | None = None
    weight_kg: float | None = None
    dimensions: Dimensions = Field(default_factory=Dimensions)
    multiplicity: float | None = None
    stock: float | None = None
    brand: str | None = None
    barcode: str | None = None
    ozon_category_id: str | None = None
    status: ProductStatus = ProductStatus.NEW
    source_import_filename: str | None = None
    source_imported_at: datetime | None = None


class ImportIssue(BaseModel):
    row_number: int | None
    field: str | None
    message: str
    severity: Literal["warning", "error"]


class ImportFieldCoverage(BaseModel):
    field: str
    label: str
    source_column: str | None = None
    present_rows: int
    missing_rows: int
    coverage_percent: float


class PriceImportVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    supplier_name: str = "Не указан"
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_rows: int
    accepted_rows: int
    section_rows: int = 0
    source_columns: list[str] = Field(default_factory=list)
    detected_columns: dict[str, str] = Field(default_factory=dict)
    field_coverage: list[ImportFieldCoverage] = Field(default_factory=list)
    products: list[SupplierProduct]
    issues: list[ImportIssue]

    @computed_field
    @property
    def rejected_rows(self) -> int:
        return max(self.total_rows - self.accepted_rows - self.section_rows, 0)

    @computed_field
    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @computed_field
    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")


class CompetitorImportResult(BaseModel):
    filename: str
    imported_rows: int
    matched_products: int
    skipped_rows: int
    source: DataSource
    issues: list[ImportIssue] = Field(default_factory=list)


class CompetitorOffer(BaseModel):
    sku: str | None = None
    title: str
    price_vat_included: float
    url: str | None = None
    match_type: Literal["exact", "analog", "reference"] = "analog"
    orders_count: int | None = None
    avg_purchase_price: float | None = None
    buyout_rate: float | None = None
    is_promo: bool = False
    source: DataSource = DataSource.MISSING


class CompetitorSnapshot(BaseModel):
    product_id: str
    offers: list[CompetitorOffer] = Field(default_factory=list)
    source: DataSource = DataSource.MISSING

    @computed_field
    @property
    def min_price(self) -> float | None:
        if not self.offers:
            return None
        return min(offer.price_vat_included for offer in self.offers)

    @computed_field
    @property
    def leader(self) -> CompetitorOffer | None:
        if not self.offers:
            return None
        return max(self.offers, key=lambda offer: offer.orders_count or 0)

    @computed_field
    @property
    def leader_url(self) -> str | None:
        leader = self.leader
        return leader.url if leader else None


class TariffRule(BaseModel):
    version: str
    category: str
    commission_percent: float
    fbs_logistics_base: float
    fbo_logistics_base: float
    acquiring_percent: float
    storage_per_liter_month: float = 0.0
    source: DataSource
    matched_ozon_category: str | None = None
    matched_ozon_product_type: str | None = None
    commission_source_label: str = "Оценка"
    warning: str | None = None


class EconomicsInput(BaseModel):
    product: SupplierProduct
    sale_price_vat_included: float
    competitor: CompetitorSnapshot | None = None
    package_cost: float = 25.0
    fulfillment_processing_cost: float = 45.0
    advertising_drr_percent: float = 12.0
    ozon_visible_discount_percent: float = 30.0
    bank_card_discount_percent: float = 8.0
    discount_percent: float = 0.0
    seller_bonus_percent: float = 45.0
    partner_program_percent: float = 0.5
    delivery_accrual_percent: float = 0.0
    other_costs: float = 0.0
    tax_regime: Literal["ip_usn_6", "osno"] = "ip_usn_6"
    use_vat: bool = False
    vat_rate: float = 0.22
    profit_tax_rate: float = 0.20
    usn_tax_rate: float = 0.06
    usn_additional_contribution_rate: float = 0.01
    usn_additional_income_threshold: float = 300_000.0
    apply_usn_additional_contribution: bool = True
    target_margin_percent: float = 15.0
    fulfillment_model: Literal["fbs", "fbo", "real_fbs"] = "fbs"
    fast_payout_fee_percent: float = 2.45
    designer_content_percent: float = 4.0
    business_fulfillment_pickup_percent: float = 0.0
    fbs_supplier_pickup_daily_cost: float = 2500.0
    fbs_ozon_sc_delivery_daily_cost: float = 600.0
    fbs_orders_per_day_scenarios: list[int] = Field(
        default_factory=lambda: [1, 5, 10, 20, 40],
    )


class DrrScenario(BaseModel):
    drr_percent: float
    advertising: float
    profit_before_tax: float
    profit_tax: float
    net_profit: float
    fast_payout_fee_percent: float
    fast_payout_fee: float
    designer_content_percent: float
    designer_content_cost: float
    business_fulfillment_pickup_percent: float
    business_fulfillment_pickup_cost: float
    business_extra_costs_total: float
    business_net_profit: float
    margin_percent: float
    break_even_price_vat_included: float
    recommendation: RecommendationStatus


class FbsBatchScenario(BaseModel):
    orders_per_day: int
    supplier_pickup_daily_cost: float
    ozon_sc_delivery_daily_cost: float
    fixed_costs_total: float
    allocated_fixed_cost_per_order: float
    business_net_profit_after_fixed: float
    margin_percent: float
    recommendation: RecommendationStatus


class EconomicsBreakdown(BaseModel):
    product_id: str
    calculation_version: str
    source: DataSource
    tax_regime: str
    vat_applicable: bool
    vat_rate: float
    tax_income_basis: float
    tax_only_break_even_price_vat_included: float
    list_price_vat_included: float
    ozon_price_before_discount_vat_included: float
    ozon_visible_discount_percent: float
    real_fbs_price_vat_included: float
    bank_card_price_vat_included: float
    bank_card_discount_percent: float
    ozon_min_price_vat_included: float
    customer_price_after_discount: float
    effective_customer_price_after_bonus: float
    buyer_payment_price_vat_included: float
    ozon_bonus_accrual: float
    partner_program_accrual: float
    delivery_accrual: float
    marketplace_gross_accrual_vat_included: float
    ozon_services_total: float
    expected_payout_after_ozon_services: float
    estimated_competitor_price_vat_included: float | None
    sale_price_vat_included: float
    sale_price_vat_excluded: float
    purchase_price_vat_included: float
    purchase_price_vat_excluded: float
    ozon_commission_percent: float
    commission_source_label: str
    matched_ozon_category: str | None
    matched_ozon_product_type: str | None
    ozon_commission: float
    logistics: float
    acquiring: float
    package_cost: float
    fulfillment_processing_cost: float
    storage: float
    advertising: float
    advertising_drr_percent: float
    discount: float
    seller_bonus_points: float
    seller_bonus_percent: float
    seller_bonus_max_spend_percent: float
    other_costs: float
    profit_before_tax: float
    usn_tax: float
    usn_additional_contribution: float
    profit_tax: float
    net_profit: float
    fast_payout_fee_percent: float
    fast_payout_fee: float
    designer_content_percent: float
    designer_content_cost: float
    business_fulfillment_pickup_percent: float
    business_fulfillment_pickup_cost: float
    business_extra_costs_total: float
    business_net_profit: float
    business_margin_percent: float
    target_margin_percent: float
    target_business_profit: float
    max_purchase_price_break_even_vat_included: float
    supplier_discount_break_even_feasible: bool
    required_supplier_discount_break_even_amount: float
    required_supplier_discount_break_even_percent: float
    target_purchase_price_vat_included: float
    supplier_discount_target_feasible: bool
    required_supplier_discount_target_amount: float
    required_supplier_discount_target_percent: float
    expense_shares_percent: dict[str, float]
    margin_percent: float
    markup_percent: float
    cost_basis_without_commission: float
    cost_basis_with_commission: float
    total_expenses_before_tax: float
    break_even_price_vat_included: float
    recommended_price_vat_included: float
    competitiveness_gap: float | None
    recommendation: RecommendationStatus
    drr_scenarios: list[DrrScenario]
    fbs_batch_scenarios: list[FbsBatchScenario]
    warnings: list[str]
    formula: list[str]


class ProductAnalysis(BaseModel):
    product: SupplierProduct
    economics: EconomicsBreakdown
    competitor: CompetitorSnapshot
    readiness: "LaunchReadiness"


class LaunchReadiness(BaseModel):
    status: LaunchReadinessStatus
    checks: dict[str, bool]
    missing_fields: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class DashboardKpi(BaseModel):
    total_products: int
    profitable_products: int
    unprofitable_products: int
    average_margin_percent: float
    potential_profit: float
    high_risk_products: int
    competitor_below_break_even: int


class ShortlistEntry(BaseModel):
    supplier_name: str = "Не указан"
    supplier_article: str
    product_id: str
    product_snapshot: SupplierProduct | None = None
    source_import_filename: str | None = None
    source_imported_at: str | None = None
    group_name: str = ""
    subgroup_name: str = ""
    offer_quantity: int = Field(default=1, ge=1)
    purchase_price_vat_included: float | None = None
    sale_price_vat_included: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    seller_bonus_percent: float | None = None
    advertising_drr_percent: float | None = None
    package_cost: float | None = None
    fulfillment_processing_cost: float | None = None
    planned_sales_qty: int = 0
    sold_qty: int = 0
    note: str = ""


class ShortlistItem(BaseModel):
    entry: ShortlistEntry
    analysis: ProductAnalysis
