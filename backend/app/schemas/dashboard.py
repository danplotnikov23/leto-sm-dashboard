from typing import Literal

from pydantic import BaseModel


OzonDashboardPeriod = Literal["7d", "14d", "28d", "month"]


class OzonDashboardMetric(BaseModel):
    revenue_with_vat: float
    ordered_units: int


class OzonDashboardDailyPoint(BaseModel):
    date: str
    revenue_with_vat: float
    ordered_units: int


class OzonDashboardSalesResponse(BaseModel):
    period: OzonDashboardPeriod
    date_from: str
    date_to: str
    today: OzonDashboardMetric
    month: OzonDashboardMetric
    selected_period: OzonDashboardMetric
    points: list[OzonDashboardDailyPoint]
    updated_at: str
    next_refresh_at: str
    refresh_interval_seconds: int
    source: str
    is_stale: bool = False
    warning: str | None = None


class MarketplaceDashboardSalesResponse(BaseModel):
    period: OzonDashboardPeriod
    combined: OzonDashboardSalesResponse
    ozon: OzonDashboardSalesResponse | None
    yandex: OzonDashboardSalesResponse | None
    provider_errors: dict[str, str]
