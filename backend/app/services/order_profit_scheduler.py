"""Refreshes today's per-order profit snapshots every 30 minutes.

Each tick pulls today's FBS postings from Ozon (one paginated list call,
no per-order requests) and recomputes profit for all of them against the
unit economy index, which is already loaded in memory - cheap enough to run
on a fixed interval rather than staleness-checking like the daily registry.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.ozon_ads_service import OzonAdsService

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 30 * 60


class OrderProfitScheduler:
    def __init__(self, ads_service: OzonAdsService) -> None:
        self._ads_service = ads_service
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
                orders = await self._ads_service.compute_today_orders_profit()
                logger.info("Refreshed profit for %d orders today", len(orders))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a bad tick must not kill the loop
                logger.exception("Order profit scheduler tick failed")
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
