import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.schemas.dashboard import (
    OzonDashboardDailyPoint,
    OzonDashboardMetric,
    OzonDashboardSalesResponse,
)
from app.services.marketplace_dashboard_service import MarketplaceDashboardService
from app.services.yandex_market_errors import YandexMarketError


MOSCOW = ZoneInfo("Europe/Moscow")


def _response(
    source: str,
    revenue: float,
    units: int,
) -> OzonDashboardSalesResponse:
    updated_at = datetime(2026, 7, 30, 10, 0, tzinfo=MOSCOW).isoformat()
    metric = OzonDashboardMetric(
        revenue_with_vat=revenue,
        ordered_units=units,
    )
    return OzonDashboardSalesResponse(
        period="7d",
        date_from="2026-07-24",
        date_to="2026-07-30",
        today=metric,
        month=metric,
        selected_period=metric,
        points=[
            OzonDashboardDailyPoint(
                date="2026-07-30",
                revenue_with_vat=revenue,
                ordered_units=units,
            )
        ],
        updated_at=updated_at,
        next_refresh_at=updated_at,
        refresh_interval_seconds=600,
        source=source,
    )


class FakeDashboardService:
    def __init__(
        self,
        result: OzonDashboardSalesResponse | Exception,
    ) -> None:
        self._result = result

    async def get_sales_dashboard(
        self,
        period: str,
        force_refresh: bool = False,
    ) -> OzonDashboardSalesResponse:
        assert period == "7d"
        assert force_refresh is False
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class SlowDashboardService:
    async def get_sales_dashboard(
        self,
        period: str,
        force_refresh: bool = False,
    ) -> OzonDashboardSalesResponse:
        assert period == "7d"
        assert force_refresh is False
        await asyncio.sleep(0.2)
        return _response("Slow provider", 500, 1)


def test_combines_ozon_and_yandex_metrics_on_backend() -> None:
    service = MarketplaceDashboardService(
        FakeDashboardService(_response("Ozon", 1000, 2)),
        FakeDashboardService(_response("Yandex", 2500, 3)),
    )

    result = asyncio.run(service.get_sales_dashboard("7d"))

    assert result.combined.today.revenue_with_vat == 3500
    assert result.combined.today.ordered_units == 5
    assert result.combined.points[-1].revenue_with_vat == 3500
    assert result.provider_errors == {}


def test_keeps_ozon_when_yandex_is_temporarily_unavailable() -> None:
    service = MarketplaceDashboardService(
        FakeDashboardService(_response("Ozon", 1000, 2)),
        FakeDashboardService(YandexMarketError("Яндекс временно недоступен")),
    )

    result = asyncio.run(service.get_sales_dashboard("7d"))

    assert result.ozon is not None
    assert result.yandex is None
    assert result.combined.today.revenue_with_vat == 1000
    assert result.combined.is_stale is True
    assert result.provider_errors["yandex"] == "Яндекс временно недоступен"


def test_returns_available_provider_when_another_provider_times_out() -> None:
    service = MarketplaceDashboardService(
        FakeDashboardService(_response("Ozon", 1000, 2)),
        SlowDashboardService(),
        provider_timeout_seconds=0.01,
    )

    result = asyncio.run(service.get_sales_dashboard("7d"))

    assert result.ozon is not None
    assert result.yandex is None
    assert result.combined.today.revenue_with_vat == 1000
    assert result.combined.is_stale is True
    assert "отвечает дольше 0.01 сек" in result.provider_errors["yandex"]
