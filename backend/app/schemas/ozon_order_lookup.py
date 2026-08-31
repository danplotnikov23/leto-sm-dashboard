from pydantic import BaseModel


class OzonOrderItem(BaseModel):
    offer_id: str
    sku: str | None = None
    name: str
    quantity: int
    price_with_vat: float
    revenue_without_vat: float
    unit_economy_matched: bool
    cost_with_commission: float | None = None
    profit_before_tax: float | None = None
    net_profit: float | None = None
    unit_economy_price: float | None = None
    markup_percent: float | None = None
    ozon_commission_rub: float | None = None
    ozon_commission_percent: float | None = None
    unit_economy_cost: float | None = None
    logistics_compensation: float | None = None


class OzonOrderLookupResponse(BaseModel):
    posting_number: str
    order_number: str
    status: str
    status_label: str
    is_cancelled: bool
    in_process_at: str | None = None
    items: list[OzonOrderItem]
    revenue_without_vat_total: float
    net_profit_total: float | None = None
    unit_economy_version: str | None = None
    warning: str | None = None
    computed_at: str | None = None
    delivery_address: str | None = None
    delivery_comment: str | None = None
    delivery_method_name: str | None = None
    delivery_price_transferred: float | None = None
    lift_option_code: str | None = None
    lift_option_label: str | None = None
    lift_price: float | None = None
    lift_floor: str | None = None
    logistics_compensation_total: float | None = None
    delivery_total_transferred: float | None = None
    delivery_cost_actual: float | None = None
    delivery_result: float | None = None
    net_profit_with_delivery_transferred: float | None = None
    net_profit_with_delivery_actual: float | None = None


class OzonOrderDeliveryActualCostInput(BaseModel):
    actual_cost: float


class OzonAdSpendForDateResponse(BaseModel):
    date: str
    ad_spend_without_vat: float | None = None
    warning: str | None = None


class OzonBatchDeliveryCalculationResult(BaseModel):
    posting_number: str
    status: str
    calculated_cost: float | None = None
    message: str | None = None


class OzonBatchDeliveryCalculationResponse(BaseModel):
    total_orders: int
    calculated_count: int
    skipped_count: int
    failed_count: int
    results: list[OzonBatchDeliveryCalculationResult]
    orders: list[OzonOrderLookupResponse]


class OzonTodayOrdersSummary(BaseModel):
    orders_count: int
    matched_orders_count: int
    revenue_without_vat_total: float
    net_profit_before_ads_total: float | None = None
    ad_spend_without_vat: float | None = None
    net_profit_total: float | None = None
    net_profit_and_delivery_total: float | None = None
    warning: str | None = None
    computed_at: str
