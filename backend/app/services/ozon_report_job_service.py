import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from uuid import uuid4

from app.core.config import Settings
from app.schemas.ozon import OzonReportJobResponse, OzonSkuEfficiencyResponse
from app.services.ozon_ad_report_repository import (
    OzonAdReportRepository,
    OzonReportJobRecord,
)
from app.services.ozon_ads_service import OzonAdsService
from app.services.ozon_period_validation import validate_ozon_report_period
from app.services.unit_economy_index_service import UnitEconomyIndexService


REPORT_TYPE_TOTAL_SALES = "ozon_total_sales_report"
CACHE_SCHEMA_VERSION = "v5"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"


@dataclass(slots=True)
class OzonReportJob:
    job_id: str
    campaign_id: str
    date_from: str
    date_to: str
    status: str
    phase: str
    progress_percent: int
    message: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    unit_economy_signature: str = ""
    cache_key: str = ""
    result_source: str | None = None
    result: OzonSkuEfficiencyResponse | None = None
    task: asyncio.Task[None] | None = None


class OzonReportJobService:
    def __init__(
        self,
        settings: Settings,
        unit_economy_index_service: UnitEconomyIndexService,
        ozon_ad_report_repository: OzonAdReportRepository,
    ) -> None:
        self._settings = settings
        self._unit_economy_index_service = unit_economy_index_service
        self._ozon_ad_report_repository = ozon_ad_report_repository
        self._jobs: dict[str, OzonReportJob] = {}
        self._lock = asyncio.Lock()
        self._ozon_queue = asyncio.Semaphore(1)

    async def create_total_sales_report_job(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonReportJobResponse:
        validate_ozon_report_period(date_from, date_to)

        unit_economy_signature = self._build_unit_economy_signature(date_from, date_to)
        cache_key = _build_cache_key(
            campaign_id,
            date_from,
            date_to,
            unit_economy_signature,
        )
        cached_result = await self._ozon_ad_report_repository.get_total_sales_cached_result(
            cache_key
        )
        if cached_result is not None:
            await self._cancel_other_active_jobs(cache_key)
            job = OzonReportJob(
                job_id=str(uuid4()),
                campaign_id=campaign_id,
                date_from=date_from,
                date_to=date_to,
                status=JOB_STATUS_SUCCEEDED,
                phase="cache",
                progress_percent=100,
                message="Готовый отчёт загружен из кэша. Ozon API не вызывался.",
                created_at=_utcnow(),
                started_at=_utcnow(),
                finished_at=_utcnow(),
                unit_economy_signature=unit_economy_signature,
                cache_key=cache_key,
                result_source="cache",
                result=cached_result,
            )
            async with self._lock:
                self._jobs[job.job_id] = job
                self._cleanup_finished_jobs()
            await self._persist_job(job)
            return self._to_response(job)

        async with self._lock:
            existing_job = self._find_active_duplicate(campaign_id, date_from, date_to)
            if existing_job is not None:
                return self._to_response(existing_job)

        await self._cancel_other_active_jobs(cache_key)

        existing_record = await self._ozon_ad_report_repository.find_active_report_job(
            REPORT_TYPE_TOTAL_SALES,
            campaign_id,
            date_from,
            date_to,
            unit_economy_signature,
        )
        if existing_record is not None:
            return _record_to_response(existing_record)

        job = OzonReportJob(
            job_id=str(uuid4()),
            campaign_id=campaign_id,
            date_from=date_from,
            date_to=date_to,
            status=JOB_STATUS_QUEUED,
            phase="queued",
            progress_percent=5,
            message="Отчёт поставлен в очередь. Ozon считает тяжёлые отчёты последовательно.",
            created_at=_utcnow(),
            unit_economy_signature=unit_economy_signature,
            cache_key=cache_key,
        )
        async with self._lock:
            self._jobs[job.job_id] = job
            self._cleanup_finished_jobs()

        await self._persist_job(job)
        job.task = asyncio.create_task(self._run_total_sales_report_job(job.job_id))
        return self._to_response(job)

    async def get_job(self, job_id: str) -> OzonReportJobResponse | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return self._to_response(job)

        record = await self._ozon_ad_report_repository.get_report_job(job_id)
        return _record_to_response(record) if record is not None else None

    async def get_job_result(self, job_id: str) -> OzonSkuEfficiencyResponse | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.result is not None:
                return job.result

        record = await self._ozon_ad_report_repository.get_report_job(job_id)
        if record is None or record.status != JOB_STATUS_SUCCEEDED:
            return None

        return await self._ozon_ad_report_repository.get_total_sales_cached_result(
            record.cache_key
        )

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [
                job.task
                for job in self._jobs.values()
                if job.task is not None and not job.task.done()
            ]

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_total_sales_report_job(self, job_id: str) -> None:
        async with self._ozon_queue:
            job = await self._mark_running(job_id)
            if job is None:
                return

            try:
                service = OzonAdsService(
                    self._settings,
                    self._unit_economy_index_service,
                    self._ozon_ad_report_repository,
                )
                result_task = asyncio.create_task(
                    service.get_total_sales_report_from_api(
                        job.campaign_id,
                        job.date_from,
                        job.date_to,
                    )
                )
                result = await self._wait_for_result(job_id, result_task)
            except asyncio.CancelledError:
                return
            except TimeoutError as exc:
                await self._mark_failed(job_id, str(exc))
                return
            except Exception as exc:
                await self._mark_failed(job_id, str(exc))
                return

            await self._mark_succeeded(job_id, result)

    async def _wait_for_result(
        self,
        job_id: str,
        result_task: asyncio.Task[OzonSkuEfficiencyResponse],
    ) -> OzonSkuEfficiencyResponse:
        started_at = _utcnow()
        timeout_seconds = max(self._settings.ozon_report_job_timeout_seconds, 60)
        progress = 35

        while not result_task.done():
            elapsed_seconds = (_utcnow() - started_at).total_seconds()
            if elapsed_seconds > timeout_seconds:
                result_task.cancel()
                await asyncio.gather(result_task, return_exceptions=True)
                raise TimeoutError(
                    "Ozon report job timed out. Ozon слишком долго готовит рекламные "
                    "батчи; попробуй меньший период или повтори позже."
                )

            next_progress = min(
                92,
                35 + int((elapsed_seconds / timeout_seconds) * 55),
            )
            if next_progress > progress:
                progress = next_progress
                await self._mark_progress(
                    job_id,
                    progress,
                    (
                        "Ozon готовит рекламные батчи, backend ждёт файлы отчётов "
                        "и сохраняет промежуточный кэш. Повторный запуск этого же "
                        "периода будет быстрее."
                    ),
                )

            await asyncio.sleep(5)

        return await result_task

    async def _mark_running(self, job_id: str) -> OzonReportJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            job.status = JOB_STATUS_RUNNING
            job.phase = "ozon"
            job.progress_percent = 35
            job.message = (
                "Backend получает рекламные отчёты Ozon, продажи Seller API и применяет юнитку."
            )
            job.started_at = _utcnow()
        await self._persist_job(job)
        return job

    async def _mark_succeeded(
        self,
        job_id: str,
        result: OzonSkuEfficiencyResponse,
    ) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return

            job.status = JOB_STATUS_SUCCEEDED
            job.phase = "done"
            job.progress_percent = 100
            job.message = "Отчёт готов и сохранён в кэше."
            job.finished_at = _utcnow()
            job.result_source = "ozon"
            job.result = result
        await self._ozon_ad_report_repository.save_total_sales_cached_result(
            job.cache_key,
            job.unit_economy_signature,
            result,
        )
        await self._persist_job(job)

    async def _mark_progress(
        self,
        job_id: str,
        progress_percent: int,
        message: str,
    ) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JOB_STATUS_RUNNING:
                return

            job.progress_percent = max(job.progress_percent, progress_percent)
            job.message = message

        await self._persist_job(job)

    async def _mark_failed(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return

            job.status = JOB_STATUS_FAILED
            job.phase = "failed"
            job.progress_percent = 100
            job.message = "Отчёт не создан."
            job.error = error
            job.finished_at = _utcnow()
        await self._persist_job(job)

    async def _cancel_other_active_jobs(self, cache_key: str) -> None:
        message = "Отчёт отменён: запущен новый период."
        cancelled_job_ids = await self._ozon_ad_report_repository.cancel_active_report_jobs(
            REPORT_TYPE_TOTAL_SALES,
            cache_key,
            message,
        )
        if not cancelled_job_ids:
            return

        async with self._lock:
            for job_id in cancelled_job_ids:
                job = self._jobs.get(job_id)
                if job is None:
                    continue

                job.status = JOB_STATUS_CANCELLED
                job.phase = "cancelled"
                job.progress_percent = 100
                job.message = message
                job.error = None
                job.finished_at = _utcnow()
                if job.task is not None and not job.task.done():
                    job.task.cancel()

    def _find_active_duplicate(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonReportJob | None:
        for job in self._jobs.values():
            if (
                job.campaign_id == campaign_id
                and job.date_from == date_from
                and job.date_to == date_to
                and job.status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING}
            ):
                return job

        return None

    async def _persist_job(self, job: OzonReportJob) -> None:
        await self._ozon_ad_report_repository.upsert_report_job(
            OzonReportJobRecord(
                job_id=job.job_id,
                report_type=REPORT_TYPE_TOTAL_SALES,
                campaign_id=job.campaign_id,
                date_from=job.date_from,
                date_to=job.date_to,
                unit_economy_signature=job.unit_economy_signature,
                cache_key=job.cache_key,
                status=job.status,
                phase=job.phase,
                progress_percent=job.progress_percent,
                message=job.message,
                error=job.error,
                result_source=job.result_source,
                created_at=_format_dt(job.created_at) or "",
                started_at=_format_dt(job.started_at),
                finished_at=_format_dt(job.finished_at),
            )
        )

    def _build_unit_economy_signature(self, date_from: str, date_to: str) -> str:
        segments = self._unit_economy_index_service.build_period_segments(
            date_from,
            date_to,
        )
        return "|".join(
            (
                f"{segment.date_from}:{segment.date_to}:"
                f"{segment.version.valid_from}:"
                f"{segment.version.version_id}"
            )
            for segment in segments
        )

    def _cleanup_finished_jobs(self) -> None:
        finished_jobs = [
            job
            for job in self._jobs.values()
            if job.finished_at is not None
            and (_utcnow() - job.finished_at).total_seconds() > 60 * 60 * 6
        ]
        for job in finished_jobs:
            self._jobs.pop(job.job_id, None)

    def _to_response(self, job: OzonReportJob) -> OzonReportJobResponse:
        return OzonReportJobResponse(
            job_id=job.job_id,
            campaign_id=job.campaign_id,
            date_from=job.date_from,
            date_to=job.date_to,
            status=job.status,
            phase=job.phase,
            progress_percent=job.progress_percent,
            message=job.message,
            result_ready=job.result is not None,
            result_source=job.result_source,
            error=job.error,
            created_at=_format_dt(job.created_at),
            started_at=_format_dt(job.started_at),
            finished_at=_format_dt(job.finished_at),
        )


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _build_cache_key(
    campaign_id: str,
    date_from: str,
    date_to: str,
    unit_economy_signature: str,
) -> str:
    raw_key = (
        f"{CACHE_SCHEMA_VERSION}:"
        f"{REPORT_TYPE_TOTAL_SALES}:"
        f"{campaign_id}:"
        f"{date_from}:"
        f"{date_to}:"
        f"{unit_economy_signature}"
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _record_to_response(record: OzonReportJobRecord) -> OzonReportJobResponse:
    return OzonReportJobResponse(
        job_id=record.job_id,
        campaign_id=record.campaign_id,
        date_from=record.date_from,
        date_to=record.date_to,
        status=record.status,
        phase=record.phase,
        progress_percent=record.progress_percent,
        message=record.message,
        result_ready=record.status == JOB_STATUS_SUCCEEDED,
        result_source=record.result_source,
        error=record.error,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )
