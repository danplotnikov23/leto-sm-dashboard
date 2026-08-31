"""Fires the daily net-profit snapshot at fixed Moscow-time checkpoints.

12:00 computes the "final" snapshot for yesterday, once - the day is fully
over by then, so there's nothing to refresh.

From 09:00 onward, "preliminary" for today is recomputed every hour (it's a
20-60s call against the live Ozon API - cheap enough now that ad spend goes
through the synchronous /statistics/expense endpoint instead of the
per-campaign report flow). Each run overwrites the same (date, "preliminary")
row rather than adding new ones.

State lives in the snapshots table itself (via computed_at), so a restart
mid-day doesn't cause a duplicate or a missed run - it just resumes from
whatever was last computed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.ozon_ad_report_repository import OzonAdReportRepository
from app.services.ozon_ads_service import OzonAdsService

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
FINAL_RUN_HOUR = 12
PRELIMINARY_START_HOUR = 9
PRELIMINARY_REFRESH_INTERVAL = timedelta(hours=1)
POLL_INTERVAL_SECONDS = 60


class DailyProfitScheduler:
    def __init__(
        self,
        ads_service: OzonAdsService,
        repository: OzonAdReportRepository,
    ) -> None:
        self._ads_service = ads_service
        self._repository = repository
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a bad tick must not kill the loop
                logger.exception("Daily profit scheduler tick failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        now = datetime.now(MOSCOW_TZ)
        if now.hour >= FINAL_RUN_HOUR:
            yesterday = (now.date() - timedelta(days=1)).isoformat()
            await self._run_if_missing(yesterday, "final")
        if now.hour >= PRELIMINARY_START_HOUR:
            today = now.date().isoformat()
            await self._run_if_stale(today, "preliminary", now)

    async def _run_if_missing(self, date_str: str, run_type: str) -> None:
        existing = await self._repository.list_daily_profit_snapshots(limit=1000)
        already_done = any(
            snapshot.date == date_str and snapshot.run_type == run_type
            for snapshot in existing
        )
        if already_done:
            return

        logger.info("Computing daily profit snapshot %s (%s)", date_str, run_type)
        await self._ads_service.compute_daily_profit_snapshot(date_str, run_type)

    async def _run_if_stale(
        self,
        date_str: str,
        run_type: str,
        now: datetime,
    ) -> None:
        existing = await self._repository.list_daily_profit_snapshots(limit=1000)
        current = next(
            (
                snapshot
                for snapshot in existing
                if snapshot.date == date_str and snapshot.run_type == run_type
            ),
            None,
        )
        if current is not None:
            computed_at = datetime.fromisoformat(current.computed_at)
            age = now - computed_at.astimezone(MOSCOW_TZ)
            if age < PRELIMINARY_REFRESH_INTERVAL:
                return

        logger.info("Computing daily profit snapshot %s (%s)", date_str, run_type)
        await self._ads_service.compute_daily_profit_snapshot(date_str, run_type)


async def run_manual_backfill(
    ads_service: OzonAdsService,
    date_str: str,
    run_type: str = "final",
) -> None:
    await ads_service.compute_daily_profit_snapshot(date_str, run_type)
