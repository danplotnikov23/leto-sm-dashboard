import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.ozon_dashboard_service import OzonDashboardService


class FakeSellerAnalyticsClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get_analytics_sales_by_day(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        self.calls += 1
        assert date_from == "2026-07-01"
        assert date_to == "2026-07-29"
        return [
            {
                "dimensions": [{"id": "2026-07-28", "name": "28 июля"}],
                "metrics": [2, 2000],
            },
            {
                "dimensions": [{"id": "2026-07-29", "name": "29 июля"}],
                "metrics": ["3", "4500.50"],
            },
        ]


def test_dashboard_aggregates_periods_and_reuses_cache() -> None:
    client = FakeSellerAnalyticsClient()
    moscow = ZoneInfo("Europe/Moscow")
    service = OzonDashboardService(
        client,
        clock=lambda: datetime(2026, 7, 29, 12, 30, tzinfo=moscow),
    )

    first = asyncio.run(service.get_sales_dashboard("7d"))
    second = asyncio.run(service.get_sales_dashboard("month"))

    assert client.calls == 1
    assert len(first.points) == 7
    assert first.today.revenue_with_vat == 4500.50
    assert first.today.ordered_units == 3
    assert first.month.revenue_with_vat == 6500.50
    assert first.month.ordered_units == 5
    assert first.selected_period.revenue_with_vat == 6500.50
    assert second.date_from == "2026-07-01"
    assert second.selected_period.revenue_with_vat == 6500.50
