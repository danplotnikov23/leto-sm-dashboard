import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol
from zoneinfo import ZoneInfo

from app.schemas.dashboard import (
    OzonDashboardDailyPoint,
    OzonDashboardMetric,
    OzonDashboardPeriod,
    OzonDashboardSalesResponse,
)
from app.services.ozon_errors import OzonApiError


class SellerAnalyticsClient(Protocol):
    async def get_analytics_sales_by_day(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class _DashboardCacheEntry:
    points: tuple[OzonDashboardDailyPoint, ...]
    updated_at: datetime
    expires_at_monotonic: float


class OzonDashboardService:
    _cache_ttl_seconds = 540
    _refresh_interval_seconds = 600
    _moscow_timezone = ZoneInfo("Europe/Moscow")

    def __init__(
        self,
        seller_client: SellerAnalyticsClient,
        clock: Callable[[], datetime] | None = None,
        source: str = "Ozon Seller API /v1/analytics/data",
        recoverable_errors: tuple[type[Exception], ...] = (OzonApiError,),
        stale_warning: str = (
            "Ozon временно не ответил. Показаны последние сохранённые данные."
        ),
    ) -> None:
        self._seller_client = seller_client
        self._clock = clock or (
            lambda: datetime.now(tz=self._moscow_timezone)
        )
        self._source = source
        self._recoverable_errors = recoverable_errors
        self._stale_warning = stale_warning
        self._cache: dict[tuple[str, str], _DashboardCacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    async def get_sales_dashboard(
        self,
        period: OzonDashboardPeriod,
        force_refresh: bool = False,
    ) -> OzonDashboardSalesResponse:
        now = self._normalized_now()
        today = now.date()
        month_start = today.replace(day=1)
        rolling_start = today - timedelta(days=27)
        fetch_start = min(month_start, rolling_start)
        cache_key = (fetch_start.isoformat(), today.isoformat())

        entry, is_stale, warning = await self._get_points(
            cache_key=cache_key,
            force_refresh=force_refresh,
            now=now,
        )
        selected_start = _period_start(period, today)
        points_by_date = {date.fromisoformat(point.date): point for point in entry.points}
        selected_points = [
            points_by_date.get(
                current_date,
                OzonDashboardDailyPoint(
                    date=current_date.isoformat(),
                    revenue_with_vat=0,
                    ordered_units=0,
                ),
            )
            for current_date in _date_range(selected_start, today)
        ]
        today_point = points_by_date.get(today)
        month_points = [
            point
            for point in entry.points
            if month_start <= date.fromisoformat(point.date) <= today
        ]

        return OzonDashboardSalesResponse(
            period=period,
            date_from=selected_start.isoformat(),
            date_to=today.isoformat(),
            today=_metric_from_points([today_point] if today_point is not None else []),
            month=_metric_from_points(month_points),
            selected_period=_metric_from_points(selected_points),
            points=selected_points,
            updated_at=entry.updated_at.isoformat(),
            next_refresh_at=(
                entry.updated_at + timedelta(seconds=self._refresh_interval_seconds)
            ).isoformat(),
            refresh_interval_seconds=self._refresh_interval_seconds,
            source=self._source,
            is_stale=is_stale,
            warning=warning,
        )

    async def _get_points(
        self,
        cache_key: tuple[str, str],
        force_refresh: bool,
        now: datetime,
    ) -> tuple[_DashboardCacheEntry, bool, str | None]:
        cached = self._cache.get(cache_key)
        if (
            cached is not None
            and not force_refresh
            and cached.expires_at_monotonic > time.monotonic()
        ):
            return cached, False, None

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if (
                cached is not None
                and not force_refresh
                and cached.expires_at_monotonic > time.monotonic()
            ):
                return cached, False, None

            try:
                raw_rows = await self._seller_client.get_analytics_sales_by_day(
                    cache_key[0],
                    cache_key[1],
                )
                points = tuple(_parse_daily_points(raw_rows))
                entry = _DashboardCacheEntry(
                    points=points,
                    updated_at=now,
                    expires_at_monotonic=time.monotonic() + self._cache_ttl_seconds,
                )
                self._cache[cache_key] = entry
                return entry, False, None
            except self._recoverable_errors:
                if cached is None:
                    raise

                return (
                    cached,
                    True,
                    self._stale_warning,
                )

    def _normalized_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            return now.replace(tzinfo=self._moscow_timezone)
        return now.astimezone(self._moscow_timezone)


def _period_start(period: OzonDashboardPeriod, today: date) -> date:
    if period == "7d":
        return today - timedelta(days=6)
    if period == "14d":
        return today - timedelta(days=13)
    if period == "28d":
        return today - timedelta(days=27)
    return today.replace(day=1)


def _date_range(date_from: date, date_to: date) -> list[date]:
    day_count = (date_to - date_from).days
    return [date_from + timedelta(days=offset) for offset in range(day_count + 1)]


def _parse_daily_points(
    rows: list[dict[str, object]],
) -> list[OzonDashboardDailyPoint]:
    totals: dict[date, tuple[Decimal, int]] = {}

    for row in rows:
        dimensions = row.get("dimensions")
        metrics = row.get("metrics")
        if (
            not isinstance(dimensions, list)
            or not dimensions
            or not isinstance(metrics, list)
            or len(metrics) < 2
        ):
            continue

        dimension = dimensions[0]
        if not isinstance(dimension, dict):
            continue

        raw_day = dimension.get("id") or dimension.get("name")
        if raw_day is None:
            continue

        try:
            row_date = date.fromisoformat(str(raw_day)[:10])
        except ValueError:
            continue

        ordered_units = _to_int(metrics[0])
        revenue = _to_decimal(metrics[1])
        current_revenue, current_units = totals.get(row_date, (Decimal("0"), 0))
        totals[row_date] = (
            current_revenue + revenue,
            current_units + ordered_units,
        )

    return [
        OzonDashboardDailyPoint(
            date=row_date.isoformat(),
            revenue_with_vat=round(float(revenue), 2),
            ordered_units=ordered_units,
        )
        for row_date, (revenue, ordered_units) in sorted(totals.items())
    ]


def _metric_from_points(
    points: list[OzonDashboardDailyPoint],
) -> OzonDashboardMetric:
    return OzonDashboardMetric(
        revenue_with_vat=round(sum(point.revenue_with_vat for point in points), 2),
        ordered_units=sum(point.ordered_units for point in points),
    )


def _to_decimal(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal("0")

    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def _to_int(value: object) -> int:
    return int(_to_decimal(value))
