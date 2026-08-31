from pydantic import BaseModel


class UnitEconomyProduct(BaseModel):
    row_number: int
    offer_id: str
    ozon_sku: str | None
    title: str | None
    category: str | None = None
    sale_schema: str | None
    price_before_discount_with_vat: float | None = None
    price_with_vat: float | None
    price_without_vat: float | None
    cost_without_vat: float | None
    ozon_commission: float | None
    ad_cost: float | None
    expense_cost: float | None
    expense_with_ozon_commission: float | None
    logistics_compensation: float | None = None
    profit_before_tax: float | None
    tax: float | None
    net_profit: float | None
    profitability: float | None


class UnitEconomyVersionSummary(BaseModel):
    valid_from: str
    sheet_name: str
    workbook_path: str
    row_count: int
    indexed_offer_ids: int
    indexed_skus: int
    version_id: str


class UnitEconomyLookupResponse(BaseModel):
    found: bool
    product: UnitEconomyProduct | None = None


class UnitEconomyIndexSummary(BaseModel):
    sheet_name: str
    row_count: int
    indexed_offer_ids: int
    indexed_skus: int
    active_version: str | None = None
    versions: list[UnitEconomyVersionSummary] = []
