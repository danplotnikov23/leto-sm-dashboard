from pydantic import BaseModel


class OzonDailyProfitSnapshot(BaseModel):
    date: str
    run_type: str
    ordered_units: int
    cancelled_units: int
    net_units: int
    revenue_with_vat: float
    revenue_without_vat: float
    profit_before_ads: float | None = None
    ad_spend_without_vat: float | None = None
    net_profit: float | None = None
    # Only orders with a manually-entered "фактическая доставка" contribute a
    # known delivery deviation - see OzonAdsService.compute_daily_profit_snapshot.
    # None on snapshots computed before this field existed (needs a recompute
    # to backfill), not the same as "zero deviation".
    net_profit_and_delivery: float | None = None
    unit_economy_version: str | None = None
    warning: str | None = None
    computed_at: str


class OzonDailyProfitRegistryResponse(BaseModel):
    snapshots: list[OzonDailyProfitSnapshot]
