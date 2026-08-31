from pydantic import BaseModel


class PriceUpdateProductMatch(BaseModel):
    offer_id: str
    sku: str | None = None
    name: str
    category: str | None = None
    current_price_before_discount: float | None = None
    current_price_with_discount: float | None = None
    current_min_price: float | None = None
    current_vat_percent: float | None = None
    current_markup_percent: float | None = None
    template_cost: float | None = None
    unit_economy_cost: float | None = None
    unit_economy_price_before_discount: float | None = None
    unit_economy_expense_cost: float | None = None
    unit_economy_matched: bool


class PriceUpdateSearchResponse(BaseModel):
    query: str
    category: str | None = None
    total_rows_in_template: int
    matches: list[PriceUpdateProductMatch]


class PriceUpdateCategory(BaseModel):
    category: str
    product_count: int


class PriceUpdateCategoriesResponse(BaseModel):
    categories: list[PriceUpdateCategory]


class PriceUpdateItem(BaseModel):
    offer_id: str
    new_price_with_discount: float
