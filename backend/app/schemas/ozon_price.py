from pydantic import BaseModel, Field


class OzonPriceSnapshot(BaseModel):
    offer_id: str
    product_id: str | None = None
    sku: str | None = None
    title: str | None = None
    fetched_at: str
    price_with_vat: float | None = None
    old_price_with_vat: float | None = None
    min_price_with_vat: float | None = None
    marketing_seller_price_with_vat: float | None = None
    net_price: float | None = None
    vat: float | None = None
    source: str = "ozon_seller_api_v5_product_info_prices"
    raw_price: dict[str, object] = Field(default_factory=dict)


class OzonPriceSnapshotResponse(BaseModel):
    items: list[OzonPriceSnapshot]
