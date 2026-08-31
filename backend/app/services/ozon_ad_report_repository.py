import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from app.schemas.ozon import OzonPromotionInfo
from app.schemas.ozon import (
    OzonSkuEfficiencyResponse,
    OzonSkuEfficiencyRow,
    OzonStatisticsReportStatus,
    OzonStoredReportSummary,
)
from app.schemas.ozon_ad_attribution import (
    OzonAdAttributionResponse,
    OzonPromotionAnalyticsImportSummary,
)
from app.schemas.ozon_daily_profit import OzonDailyProfitSnapshot
from app.schemas.ozon_order_lookup import OzonOrderLookupResponse
from app.schemas.ozon_product_sales import OzonProductSalesImportSummary
from app.services.ozon_product_sales_report_parser import ProductSalesRow
from app.services.ozon_total_sales_report_parser import OzonTotalSalesReportRow
from app.services.unit_economy_index_service import UnitEconomyWorkbookVersion


@dataclass(frozen=True, slots=True)
class OzonReportJobRecord:
    job_id: str
    report_type: str
    campaign_id: str
    date_from: str
    date_to: str
    unit_economy_signature: str
    cache_key: str
    status: str
    phase: str
    progress_percent: int
    message: str
    error: str | None
    result_source: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class OzonAdReportRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    async def upsert_report_status(
        self,
        status: OzonStatisticsReportStatus,
        date_from: str,
        date_to: str,
        unit_economy_version: UnitEconomyWorkbookVersion | None,
    ) -> None:
        await asyncio.to_thread(
            self._upsert_report_status,
            status,
            date_from,
            date_to,
            unit_economy_version,
        )

    async def save_efficiency_result(
        self,
        response: OzonSkuEfficiencyResponse,
        raw_report_csv: str,
        unit_economy_version: UnitEconomyWorkbookVersion | None,
    ) -> None:
        await asyncio.to_thread(
            self._save_efficiency_result,
            response,
            raw_report_csv,
            unit_economy_version,
        )

    async def update_report_status(self, status: OzonStatisticsReportStatus) -> None:
        await asyncio.to_thread(self._update_report_status, status)

    async def find_report_status(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonStatisticsReportStatus | None:
        return await asyncio.to_thread(
            self._find_report_status,
            campaign_id,
            date_from,
            date_to,
        )

    async def find_active_report_status(self) -> OzonStatisticsReportStatus | None:
        return await asyncio.to_thread(self._find_active_report_status)

    async def get_efficiency_result(
        self,
        report_uuid: str,
    ) -> OzonSkuEfficiencyResponse | None:
        return await asyncio.to_thread(self._get_efficiency_result, report_uuid)

    async def get_raw_report_csv(self, report_uuid: str) -> str | None:
        return await asyncio.to_thread(self._get_raw_report_csv, report_uuid)

    async def list_reports(self, limit: int = 50) -> list[OzonStoredReportSummary]:
        normalized_limit = max(1, min(limit, 500))
        return await asyncio.to_thread(self._list_reports, normalized_limit)

    async def get_total_sales_cached_result(
        self,
        cache_key: str,
    ) -> OzonSkuEfficiencyResponse | None:
        return await asyncio.to_thread(self._get_total_sales_cached_result, cache_key)

    async def save_total_sales_cached_result(
        self,
        cache_key: str,
        unit_economy_signature: str,
        response: OzonSkuEfficiencyResponse,
    ) -> None:
        await asyncio.to_thread(
            self._save_total_sales_cached_result,
            cache_key,
            unit_economy_signature,
            response,
        )

    async def get_total_sales_rows_cache(
        self,
        date_from: str,
        date_to: str,
    ) -> list[OzonTotalSalesReportRow] | None:
        return await asyncio.to_thread(
            self._get_total_sales_rows_cache,
            date_from,
            date_to,
        )

    async def save_total_sales_rows_cache(
        self,
        date_from: str,
        date_to: str,
        rows: list[OzonTotalSalesReportRow],
    ) -> None:
        await asyncio.to_thread(
            self._save_total_sales_rows_cache,
            date_from,
            date_to,
            rows,
        )

    async def upsert_report_job(
        self,
        job: OzonReportJobRecord,
    ) -> None:
        await asyncio.to_thread(self._upsert_report_job, job)

    async def get_report_job(self, job_id: str) -> OzonReportJobRecord | None:
        return await asyncio.to_thread(self._get_report_job, job_id)

    async def find_active_report_job(
        self,
        report_type: str,
        campaign_id: str,
        date_from: str,
        date_to: str,
        unit_economy_signature: str,
    ) -> OzonReportJobRecord | None:
        return await asyncio.to_thread(
            self._find_active_report_job,
            report_type,
            campaign_id,
            date_from,
            date_to,
            unit_economy_signature,
        )

    async def save_promotion_analytics_import(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
        source_filename: str,
        response: OzonAdAttributionResponse,
    ) -> int:
        return await asyncio.to_thread(
            self._save_promotion_analytics_import,
            campaign_id,
            date_from,
            date_to,
            source_filename,
            response,
        )

    async def list_promotion_analytics_imports(
        self,
        limit: int = 100,
    ) -> list[OzonPromotionAnalyticsImportSummary]:
        normalized_limit = max(1, min(limit, 500))
        return await asyncio.to_thread(
            self._list_promotion_analytics_imports,
            normalized_limit,
        )

    async def get_promotion_analytics_import(
        self,
        import_id: int,
    ) -> OzonAdAttributionResponse | None:
        return await asyncio.to_thread(
            self._get_promotion_analytics_import,
            import_id,
        )

    async def save_product_sales_rows(self, rows: Sequence[ProductSalesRow]) -> None:
        await asyncio.to_thread(self._save_product_sales_rows, rows)

    async def save_product_sales_import(
        self,
        date_from: str,
        date_to: str,
        source_filename: str,
        sku_count: int,
        row_count: int,
        has_daily_breakdown: bool,
    ) -> int:
        return await asyncio.to_thread(
            self._save_product_sales_import,
            date_from,
            date_to,
            source_filename,
            sku_count,
            row_count,
            has_daily_breakdown,
        )

    async def list_product_sales_imports(
        self,
        limit: int = 100,
    ) -> list[OzonProductSalesImportSummary]:
        normalized_limit = max(1, min(limit, 500))
        return await asyncio.to_thread(
            self._list_product_sales_imports,
            normalized_limit,
        )

    async def get_product_sales_rows(
        self,
        date_from: str,
        date_to: str,
    ) -> list[ProductSalesRow]:
        return await asyncio.to_thread(
            self._get_product_sales_rows,
            date_from,
            date_to,
        )

    async def get_promotion_analytics_import_by_period(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonAdAttributionResponse | None:
        return await asyncio.to_thread(
            self._get_promotion_analytics_import_by_period,
            campaign_id,
            date_from,
            date_to,
        )

    async def save_daily_profit_snapshot(
        self,
        snapshot: OzonDailyProfitSnapshot,
    ) -> None:
        await asyncio.to_thread(self._save_daily_profit_snapshot, snapshot)

    async def list_daily_profit_snapshots(
        self,
        limit: int = 120,
    ) -> list[OzonDailyProfitSnapshot]:
        normalized_limit = max(1, min(limit, 1000))
        return await asyncio.to_thread(
            self._list_daily_profit_snapshots,
            normalized_limit,
        )

    async def delete_daily_profit_snapshot(self, date: str, run_type: str) -> None:
        await asyncio.to_thread(
            self._delete_daily_profit_snapshot,
            date,
            run_type,
        )

    async def save_order_profit_snapshot(
        self,
        order: OzonOrderLookupResponse,
    ) -> None:
        await asyncio.to_thread(self._save_order_profit_snapshot, order)

    async def list_order_profit_snapshots(
        self,
        since_iso: str | None = None,
        to_iso: str | None = None,
    ) -> list[OzonOrderLookupResponse]:
        return await asyncio.to_thread(
            self._list_order_profit_snapshots,
            since_iso,
            to_iso,
        )

    async def save_delivery_actual_cost(
        self,
        posting_number: str,
        actual_cost: float,
    ) -> None:
        await asyncio.to_thread(
            self._save_delivery_actual_cost,
            posting_number,
            actual_cost,
        )

    async def get_delivery_actual_cost(self, posting_number: str) -> float | None:
        return await asyncio.to_thread(
            self._get_delivery_actual_cost,
            posting_number,
        )

    async def get_delivery_actual_costs(
        self,
        posting_numbers: Sequence[str],
    ) -> dict[str, float]:
        if not posting_numbers:
            return {}
        return await asyncio.to_thread(
            self._get_delivery_actual_costs,
            list(posting_numbers),
        )

    async def cancel_active_report_jobs(
        self,
        report_type: str,
        except_cache_key: str,
        message: str,
    ) -> list[str]:
        return await asyncio.to_thread(
            self._cancel_active_report_jobs,
            report_type,
            except_cache_key,
            message,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ozon_ad_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    report_uuid TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    link TEXT,
                    ozon_created_at TEXT,
                    ozon_updated_at TEXT,
                    unit_economy_workbook_path TEXT,
                    unit_economy_version TEXT,
                    unit_economy_modified_at TEXT,
                    unit_economy_size_bytes INTEGER,
                    raw_report_csv TEXT,
                    adjustment_ad_spend_with_vat REAL NOT NULL DEFAULT 0,
                    adjustment_ad_spend_without_vat REAL NOT NULL DEFAULT 0,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_ad_reports_period
                    ON ozon_ad_reports (campaign_id, date_from, date_to);

                CREATE TABLE IF NOT EXISTS ozon_ad_report_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL REFERENCES ozon_ad_reports(id) ON DELETE CASCADE,
                    row_type TEXT NOT NULL,
                    sku TEXT NOT NULL,
                    offer_id TEXT,
                    title TEXT,
                    views INTEGER NOT NULL,
                    clicks INTEGER NOT NULL,
                    to_cart INTEGER NOT NULL,
                    orders_count INTEGER NOT NULL,
                    revenue_with_vat REAL NOT NULL,
                    revenue_without_vat REAL NOT NULL,
                    ad_spend_with_vat REAL NOT NULL,
                    ad_spend_without_vat REAL NOT NULL,
                    drr_percent REAL,
                    ctr_percent REAL,
                    average_cpc REAL,
                    model_orders INTEGER NOT NULL,
                    model_revenue_with_vat REAL NOT NULL,
                    total_ordered_amount_with_vat REAL NOT NULL,
                    unit_expense_with_ozon_commission REAL,
                    profit_before_tax REAL,
                    net_profit REAL,
                    matched_unit_economy INTEGER NOT NULL,
                    UNIQUE(report_id, row_type, sku)
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_ad_report_rows_offer_id
                    ON ozon_ad_report_rows (offer_id);

                CREATE TABLE IF NOT EXISTS ozon_total_sales_report_cache (
                    cache_key TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    unit_economy_signature TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_total_sales_report_cache_lookup
                    ON ozon_total_sales_report_cache (
                        campaign_id,
                        date_from,
                        date_to,
                        unit_economy_signature
                    );

                CREATE TABLE IF NOT EXISTS ozon_report_jobs (
                    job_id TEXT PRIMARY KEY,
                    report_type TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    unit_economy_signature TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    error TEXT,
                    result_source TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_report_jobs_lookup
                    ON ozon_report_jobs (
                        report_type,
                        campaign_id,
                        date_from,
                        date_to,
                        unit_economy_signature,
                        status,
                        updated_at
                    );

                CREATE TABLE IF NOT EXISTS ozon_total_sales_rows_cache (
                    cache_key TEXT PRIMARY KEY,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_total_sales_rows_cache_period
                    ON ozon_total_sales_rows_cache (date_from, date_to);

                CREATE TABLE IF NOT EXISTS ozon_promotion_analytics_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(campaign_id, date_from, date_to)
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_promotion_analytics_imports_period
                    ON ozon_promotion_analytics_imports (date_from, date_to);

                CREATE TABLE IF NOT EXISTS ozon_product_sales_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL,
                    offer_id TEXT,
                    title TEXT,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    ordered_units INTEGER NOT NULL,
                    redeemed_units INTEGER NOT NULL,
                    cancelled_units INTEGER NOT NULL,
                    avg_price REAL NOT NULL,
                    discount_fraction REAL NOT NULL,
                    UNIQUE(sku, date_from, date_to)
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_product_sales_rows_period
                    ON ozon_product_sales_rows (date_from, date_to);

                CREATE TABLE IF NOT EXISTS ozon_product_sales_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    sku_count INTEGER NOT NULL,
                    row_count INTEGER NOT NULL,
                    has_daily_breakdown INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(date_from, date_to)
                );

                CREATE TABLE IF NOT EXISTS ozon_daily_profit_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    run_type TEXT NOT NULL,
                    ordered_units INTEGER NOT NULL,
                    cancelled_units INTEGER NOT NULL,
                    net_units INTEGER NOT NULL,
                    revenue_with_vat REAL NOT NULL,
                    revenue_without_vat REAL NOT NULL,
                    profit_before_ads REAL,
                    ad_spend_without_vat REAL,
                    net_profit REAL,
                    unit_economy_version TEXT,
                    warning TEXT,
                    computed_at TEXT NOT NULL,
                    UNIQUE(date, run_type)
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_daily_profit_snapshots_date
                    ON ozon_daily_profit_snapshots (date);

                CREATE TABLE IF NOT EXISTS ozon_order_profit_snapshots (
                    posting_number TEXT PRIMARY KEY,
                    in_process_at TEXT,
                    computed_at TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ozon_order_profit_snapshots_in_process_at
                    ON ozon_order_profit_snapshots (in_process_at);

                CREATE TABLE IF NOT EXISTS ozon_order_delivery_actual_cost (
                    posting_number TEXT PRIMARY KEY,
                    actual_cost REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # net_profit_and_delivery was added after ozon_daily_profit_snapshots
            # already existed in deployed databases - CREATE TABLE IF NOT EXISTS
            # above is a no-op for those, so the column needs its own migration.
            # SQLite has no "ADD COLUMN IF NOT EXISTS", hence the try/except.
            try:
                connection.execute(
                    "ALTER TABLE ozon_daily_profit_snapshots "
                    "ADD COLUMN net_profit_and_delivery REAL"
                )
            except sqlite3.OperationalError as error:
                if "duplicate column name" not in str(error).lower():
                    raise
            connection.execute(
                """
                UPDATE ozon_report_jobs
                SET status = 'failed',
                    phase = 'failed',
                    progress_percent = 100,
                    message = 'Backend был перезапущен во время расчёта.',
                    error = 'Report job was interrupted by backend restart',
                    finished_at = COALESCE(finished_at, ?),
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (_utc_now(), _utc_now()),
            )

    def _upsert_report_status(
        self,
        status: OzonStatisticsReportStatus,
        date_from: str,
        date_to: str,
        unit_economy_version: UnitEconomyWorkbookVersion | None,
    ) -> None:
        now = _utc_now()
        unit_path, unit_version, unit_modified_at, unit_size = _unit_version_values(
            unit_economy_version
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_ad_reports (
                    campaign_id,
                    date_from,
                    date_to,
                    report_uuid,
                    state,
                    link,
                    ozon_created_at,
                    ozon_updated_at,
                    unit_economy_workbook_path,
                    unit_economy_version,
                    unit_economy_modified_at,
                    unit_economy_size_bytes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_uuid) DO UPDATE SET
                    campaign_id = excluded.campaign_id,
                    date_from = excluded.date_from,
                    date_to = excluded.date_to,
                    state = excluded.state,
                    link = excluded.link,
                    ozon_created_at = excluded.ozon_created_at,
                    ozon_updated_at = excluded.ozon_updated_at,
                    unit_economy_workbook_path = excluded.unit_economy_workbook_path,
                    unit_economy_version = excluded.unit_economy_version,
                    unit_economy_modified_at = excluded.unit_economy_modified_at,
                    unit_economy_size_bytes = excluded.unit_economy_size_bytes,
                    updated_at = excluded.updated_at
                """,
                (
                    status.campaign_id,
                    date_from,
                    date_to,
                    status.report_uuid,
                    status.state,
                    status.link,
                    status.created_at,
                    status.updated_at,
                    unit_path,
                    unit_version,
                    unit_modified_at,
                    unit_size,
                    now,
                    now,
                ),
            )

    def _update_report_status(self, status: OzonStatisticsReportStatus) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ozon_ad_reports
                SET state = ?,
                    link = COALESCE(?, link),
                    ozon_created_at = COALESCE(?, ozon_created_at),
                    ozon_updated_at = COALESCE(?, ozon_updated_at),
                    updated_at = ?
                WHERE report_uuid = ?
                """,
                (
                    status.state,
                    status.link,
                    status.created_at,
                    status.updated_at,
                    now,
                    status.report_uuid,
                ),
            )

    def _find_report_status(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonStatisticsReportStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT campaign_id, report_uuid, state, link, ozon_created_at, ozon_updated_at
                FROM ozon_ad_reports
                WHERE campaign_id = ?
                    AND date_from = ?
                    AND date_to = ?
                    AND state != 'IMPORTED'
                ORDER BY
                    CASE state
                        WHEN 'OK' THEN 0
                        WHEN 'IN_PROGRESS' THEN 1
                        WHEN 'NOT_STARTED' THEN 2
                        WHEN 'CREATED' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC
                LIMIT 1
                """,
                (campaign_id, date_from, date_to),
            ).fetchone()

        return _row_to_status(row)

    def _find_active_report_status(self) -> OzonStatisticsReportStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT campaign_id, report_uuid, state, link, ozon_created_at, ozon_updated_at
                FROM ozon_ad_reports
                WHERE state IN ('CREATED', 'NOT_STARTED', 'IN_PROGRESS')
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        return _row_to_status(row)

    def _save_efficiency_result(
        self,
        response: OzonSkuEfficiencyResponse,
        raw_report_csv: str,
        unit_economy_version: UnitEconomyWorkbookVersion | None,
    ) -> None:
        now = _utc_now()
        unit_path, unit_version, unit_modified_at, unit_size = _unit_version_values(
            unit_economy_version
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_ad_reports (
                    campaign_id,
                    date_from,
                    date_to,
                    report_uuid,
                    state,
                    unit_economy_workbook_path,
                    unit_economy_version,
                    unit_economy_modified_at,
                    unit_economy_size_bytes,
                    raw_report_csv,
                    adjustment_ad_spend_with_vat,
                    adjustment_ad_spend_without_vat,
                    response_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_uuid) DO UPDATE SET
                    campaign_id = excluded.campaign_id,
                    date_from = excluded.date_from,
                    date_to = excluded.date_to,
                    state = excluded.state,
                    unit_economy_workbook_path = excluded.unit_economy_workbook_path,
                    unit_economy_version = excluded.unit_economy_version,
                    unit_economy_modified_at = excluded.unit_economy_modified_at,
                    unit_economy_size_bytes = excluded.unit_economy_size_bytes,
                    raw_report_csv = excluded.raw_report_csv,
                    adjustment_ad_spend_with_vat = excluded.adjustment_ad_spend_with_vat,
                    adjustment_ad_spend_without_vat = excluded.adjustment_ad_spend_without_vat,
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    response.campaign_id,
                    response.date_from,
                    response.date_to,
                    response.report_uuid,
                    response.report_state,
                    unit_path,
                    unit_version,
                    unit_modified_at,
                    unit_size,
                    raw_report_csv,
                    response.adjustment_ad_spend_with_vat,
                    response.adjustment_ad_spend_without_vat,
                    response.model_dump_json(),
                    now,
                    now,
                ),
            )
            report_id = _select_report_id(connection, response.report_uuid)
            connection.execute(
                "DELETE FROM ozon_ad_report_rows WHERE report_id = ?",
                (report_id,),
            )
            self._insert_rows(connection, report_id, "product", response.rows)
            if response.total is not None:
                self._insert_rows(connection, report_id, "total", [response.total])

    def _insert_rows(
        self,
        connection: sqlite3.Connection,
        report_id: int,
        row_type: str,
        rows: Sequence[OzonSkuEfficiencyRow],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO ozon_ad_report_rows (
                report_id,
                row_type,
                sku,
                offer_id,
                title,
                views,
                clicks,
                to_cart,
                orders_count,
                revenue_with_vat,
                revenue_without_vat,
                ad_spend_with_vat,
                ad_spend_without_vat,
                drr_percent,
                ctr_percent,
                average_cpc,
                model_orders,
                model_revenue_with_vat,
                total_ordered_amount_with_vat,
                unit_expense_with_ozon_commission,
                profit_before_tax,
                net_profit,
                matched_unit_economy
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    report_id,
                    row_type,
                    row.sku,
                    row.offer_id,
                    row.title,
                    row.views,
                    row.clicks,
                    row.to_cart,
                    row.orders,
                    row.revenue_with_vat,
                    row.revenue_without_vat,
                    row.ad_spend_with_vat,
                    row.ad_spend_without_vat,
                    row.drr_percent,
                    row.ctr_percent,
                    row.average_cpc,
                    row.model_orders,
                    row.model_revenue_with_vat,
                    row.total_ordered_amount_with_vat,
                    row.unit_expense_with_ozon_commission,
                    row.profit_before_tax,
                    row.net_profit,
                    1 if row.matched_unit_economy else 0,
                )
                for row in rows
            ],
        )

    def _get_efficiency_result(
        self,
        report_uuid: str,
    ) -> OzonSkuEfficiencyResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json
                FROM ozon_ad_reports
                WHERE report_uuid = ? AND response_json IS NOT NULL
                """,
                (report_uuid,),
            ).fetchone()

        if row is None:
            return None

        return OzonSkuEfficiencyResponse.model_validate_json(row["response_json"])

    def _get_raw_report_csv(self, report_uuid: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT raw_report_csv
                FROM ozon_ad_reports
                WHERE report_uuid = ? AND raw_report_csv IS NOT NULL
                """,
                (report_uuid,),
            ).fetchone()

        if row is None:
            return None

        return str(row["raw_report_csv"])

    def _list_reports(self, limit: int) -> list[OzonStoredReportSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    reports.campaign_id,
                    reports.date_from,
                    reports.date_to,
                    reports.report_uuid,
                    reports.state,
                    reports.unit_economy_version,
                    reports.updated_at,
                    COUNT(product_rows.id) AS rows_count,
                    total_rows.ad_spend_without_vat AS total_ad_spend_without_vat,
                    total_rows.net_profit AS total_net_profit
                FROM ozon_ad_reports AS reports
                LEFT JOIN ozon_ad_report_rows AS product_rows
                    ON product_rows.report_id = reports.id
                    AND product_rows.row_type = 'product'
                LEFT JOIN ozon_ad_report_rows AS total_rows
                    ON total_rows.report_id = reports.id
                    AND total_rows.row_type = 'total'
                GROUP BY reports.id
                ORDER BY reports.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            OzonStoredReportSummary(
                campaign_id=row["campaign_id"],
                date_from=row["date_from"],
                date_to=row["date_to"],
                report_uuid=row["report_uuid"],
                state=row["state"],
                rows_count=int(row["rows_count"]),
                total_ad_spend_without_vat=row["total_ad_spend_without_vat"],
                total_net_profit=row["total_net_profit"],
                unit_economy_version=row["unit_economy_version"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def _save_promotion_analytics_import(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
        source_filename: str,
        response: OzonAdAttributionResponse,
    ) -> int:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_promotion_analytics_imports (
                    campaign_id,
                    date_from,
                    date_to,
                    source_filename,
                    response_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id, date_from, date_to) DO UPDATE SET
                    source_filename = excluded.source_filename,
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (
                    campaign_id,
                    date_from,
                    date_to,
                    source_filename,
                    response.model_dump_json(),
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT id FROM ozon_promotion_analytics_imports
                WHERE campaign_id = ? AND date_from = ? AND date_to = ?
                """,
                (campaign_id, date_from, date_to),
            ).fetchone()

        return int(row["id"])

    def _list_promotion_analytics_imports(
        self,
        limit: int,
    ) -> list[OzonPromotionAnalyticsImportSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, campaign_id, date_from, date_to, source_filename, created_at
                FROM ozon_promotion_analytics_imports
                ORDER BY date_from DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            OzonPromotionAnalyticsImportSummary(
                id=row["id"],
                campaign_id=row["campaign_id"],
                date_from=row["date_from"],
                date_to=row["date_to"],
                source_filename=row["source_filename"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _get_promotion_analytics_import(
        self,
        import_id: int,
    ) -> OzonAdAttributionResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json
                FROM ozon_promotion_analytics_imports
                WHERE id = ?
                """,
                (import_id,),
            ).fetchone()

        if row is None:
            return None

        return OzonAdAttributionResponse.model_validate_json(row["response_json"])

    def _save_product_sales_rows(self, rows: Sequence[ProductSalesRow]) -> None:
        if not rows:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO ozon_product_sales_rows (
                    sku, offer_id, title, date_from, date_to,
                    ordered_units, redeemed_units, cancelled_units,
                    avg_price, discount_fraction
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku, date_from, date_to) DO UPDATE SET
                    offer_id = excluded.offer_id,
                    title = excluded.title,
                    ordered_units = excluded.ordered_units,
                    redeemed_units = excluded.redeemed_units,
                    cancelled_units = excluded.cancelled_units,
                    avg_price = excluded.avg_price,
                    discount_fraction = excluded.discount_fraction
                """,
                [
                    (
                        row.sku,
                        row.offer_id,
                        row.title,
                        row.date_from,
                        row.date_to,
                        row.ordered_units,
                        row.redeemed_units,
                        row.cancelled_units,
                        row.avg_price,
                        row.discount_fraction,
                    )
                    for row in rows
                ],
            )

    def _save_product_sales_import(
        self,
        date_from: str,
        date_to: str,
        source_filename: str,
        sku_count: int,
        row_count: int,
        has_daily_breakdown: bool,
    ) -> int:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_product_sales_imports (
                    date_from, date_to, source_filename,
                    sku_count, row_count, has_daily_breakdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date_from, date_to) DO UPDATE SET
                    source_filename = excluded.source_filename,
                    sku_count = excluded.sku_count,
                    row_count = excluded.row_count,
                    has_daily_breakdown = excluded.has_daily_breakdown,
                    created_at = excluded.created_at
                """,
                (
                    date_from,
                    date_to,
                    source_filename,
                    sku_count,
                    row_count,
                    1 if has_daily_breakdown else 0,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT id FROM ozon_product_sales_imports
                WHERE date_from = ? AND date_to = ?
                """,
                (date_from, date_to),
            ).fetchone()

        return int(row["id"])

    def _list_product_sales_imports(
        self,
        limit: int,
    ) -> list[OzonProductSalesImportSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date_from, date_to, source_filename,
                       sku_count, row_count, has_daily_breakdown, created_at
                FROM ozon_product_sales_imports
                ORDER BY date_from DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            OzonProductSalesImportSummary(
                id=row["id"],
                date_from=row["date_from"],
                date_to=row["date_to"],
                source_filename=row["source_filename"],
                sku_count=row["sku_count"],
                row_count=row["row_count"],
                has_daily_breakdown=bool(row["has_daily_breakdown"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _get_product_sales_rows(
        self,
        date_from: str,
        date_to: str,
    ) -> list[ProductSalesRow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sku, offer_id, title, date_from, date_to,
                       ordered_units, redeemed_units, cancelled_units,
                       avg_price, discount_fraction
                FROM ozon_product_sales_rows
                WHERE date_from >= ? AND date_to <= ?
                """,
                (date_from, date_to),
            ).fetchall()

        return [
            ProductSalesRow(
                sku=row["sku"],
                offer_id=row["offer_id"],
                title=row["title"],
                date_from=row["date_from"],
                date_to=row["date_to"],
                ordered_units=row["ordered_units"],
                redeemed_units=row["redeemed_units"],
                cancelled_units=row["cancelled_units"],
                avg_price=row["avg_price"],
                discount_fraction=row["discount_fraction"],
            )
            for row in rows
        ]

    def _get_promotion_analytics_import_by_period(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> OzonAdAttributionResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json
                FROM ozon_promotion_analytics_imports
                WHERE campaign_id = ? AND date_from = ? AND date_to = ?
                """,
                (campaign_id, date_from, date_to),
            ).fetchone()

        if row is None:
            return None

        return OzonAdAttributionResponse.model_validate_json(row["response_json"])

    def _save_daily_profit_snapshot(self, snapshot: OzonDailyProfitSnapshot) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_daily_profit_snapshots (
                    date, run_type, ordered_units, cancelled_units, net_units,
                    revenue_with_vat, revenue_without_vat, profit_before_ads,
                    ad_spend_without_vat, net_profit, net_profit_and_delivery,
                    unit_economy_version, warning, computed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, run_type) DO UPDATE SET
                    ordered_units = excluded.ordered_units,
                    cancelled_units = excluded.cancelled_units,
                    net_units = excluded.net_units,
                    revenue_with_vat = excluded.revenue_with_vat,
                    revenue_without_vat = excluded.revenue_without_vat,
                    profit_before_ads = excluded.profit_before_ads,
                    ad_spend_without_vat = excluded.ad_spend_without_vat,
                    net_profit = excluded.net_profit,
                    net_profit_and_delivery = excluded.net_profit_and_delivery,
                    unit_economy_version = excluded.unit_economy_version,
                    warning = excluded.warning,
                    computed_at = excluded.computed_at
                """,
                (
                    snapshot.date,
                    snapshot.run_type,
                    snapshot.ordered_units,
                    snapshot.cancelled_units,
                    snapshot.net_units,
                    snapshot.revenue_with_vat,
                    snapshot.revenue_without_vat,
                    snapshot.profit_before_ads,
                    snapshot.ad_spend_without_vat,
                    snapshot.net_profit,
                    snapshot.net_profit_and_delivery,
                    snapshot.unit_economy_version,
                    snapshot.warning,
                    snapshot.computed_at,
                ),
            )

    def _list_daily_profit_snapshots(
        self,
        limit: int,
    ) -> list[OzonDailyProfitSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT date, run_type, ordered_units, cancelled_units, net_units,
                       revenue_with_vat, revenue_without_vat, profit_before_ads,
                       ad_spend_without_vat, net_profit, net_profit_and_delivery,
                       unit_economy_version, warning, computed_at
                FROM ozon_daily_profit_snapshots
                ORDER BY date DESC, run_type ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            OzonDailyProfitSnapshot(
                date=row["date"],
                run_type=row["run_type"],
                ordered_units=row["ordered_units"],
                cancelled_units=row["cancelled_units"],
                net_units=row["net_units"],
                revenue_with_vat=row["revenue_with_vat"],
                revenue_without_vat=row["revenue_without_vat"],
                profit_before_ads=row["profit_before_ads"],
                ad_spend_without_vat=row["ad_spend_without_vat"],
                net_profit=row["net_profit"],
                net_profit_and_delivery=row["net_profit_and_delivery"],
                unit_economy_version=row["unit_economy_version"],
                warning=row["warning"],
                computed_at=row["computed_at"],
            )
            for row in rows
        ]

    def _delete_daily_profit_snapshot(self, date: str, run_type: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM ozon_daily_profit_snapshots
                WHERE date = ? AND run_type = ?
                """,
                (date, run_type),
            )

    def _save_order_profit_snapshot(self, order: OzonOrderLookupResponse) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_order_profit_snapshots (
                    posting_number, in_process_at, computed_at, response_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(posting_number) DO UPDATE SET
                    in_process_at = excluded.in_process_at,
                    computed_at = excluded.computed_at,
                    response_json = excluded.response_json
                """,
                (
                    order.posting_number,
                    order.in_process_at,
                    order.computed_at,
                    order.model_dump_json(),
                ),
            )

    def _list_order_profit_snapshots(
        self,
        since_iso: str | None,
        to_iso: str | None,
    ) -> list[OzonOrderLookupResponse]:
        query = "SELECT response_json FROM ozon_order_profit_snapshots"
        params: list[str] = []
        conditions = []
        if since_iso is not None:
            conditions.append("in_process_at >= ?")
            params.append(since_iso)
        if to_iso is not None:
            conditions.append("in_process_at <= ?")
            params.append(to_iso)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY in_process_at DESC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [
            OzonOrderLookupResponse.model_validate_json(row["response_json"])
            for row in rows
        ]

    def _save_delivery_actual_cost(self, posting_number: str, actual_cost: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_order_delivery_actual_cost (
                    posting_number, actual_cost, updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(posting_number) DO UPDATE SET
                    actual_cost = excluded.actual_cost,
                    updated_at = excluded.updated_at
                """,
                (posting_number, actual_cost, _utc_now()),
            )

    def _get_delivery_actual_cost(self, posting_number: str) -> float | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT actual_cost FROM ozon_order_delivery_actual_cost WHERE posting_number = ?",
                (posting_number,),
            ).fetchone()
        return float(row["actual_cost"]) if row is not None else None

    def _get_delivery_actual_costs(self, posting_numbers: list[str]) -> dict[str, float]:
        placeholders = ",".join("?" for _ in posting_numbers)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT posting_number, actual_cost FROM ozon_order_delivery_actual_cost "
                f"WHERE posting_number IN ({placeholders})",
                posting_numbers,
            ).fetchall()
        return {row["posting_number"]: float(row["actual_cost"]) for row in rows}

    def _get_total_sales_cached_result(
        self,
        cache_key: str,
    ) -> OzonSkuEfficiencyResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json
                FROM ozon_total_sales_report_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()

        if row is None:
            return None

        return OzonSkuEfficiencyResponse.model_validate_json(row["response_json"])

    def _save_total_sales_cached_result(
        self,
        cache_key: str,
        unit_economy_signature: str,
        response: OzonSkuEfficiencyResponse,
    ) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_total_sales_report_cache (
                    cache_key,
                    campaign_id,
                    date_from,
                    date_to,
                    unit_economy_signature,
                    response_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    campaign_id = excluded.campaign_id,
                    date_from = excluded.date_from,
                    date_to = excluded.date_to,
                    unit_economy_signature = excluded.unit_economy_signature,
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    cache_key,
                    response.campaign_id,
                    response.date_from,
                    response.date_to,
                    unit_economy_signature,
                    response.model_dump_json(),
                    now,
                    now,
                ),
            )

    def _get_total_sales_rows_cache(
        self,
        date_from: str,
        date_to: str,
    ) -> list[OzonTotalSalesReportRow] | None:
        cache_key = _total_sales_rows_cache_key(date_from, date_to)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT rows_json
                FROM ozon_total_sales_rows_cache
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()

        if row is None:
            return None

        raw_rows = json.loads(row["rows_json"])
        if not isinstance(raw_rows, list):
            return None

        return [_total_sales_row_from_dict(raw_row) for raw_row in raw_rows]

    def _save_total_sales_rows_cache(
        self,
        date_from: str,
        date_to: str,
        rows: list[OzonTotalSalesReportRow],
    ) -> None:
        cache_key = _total_sales_rows_cache_key(date_from, date_to)
        now = _utc_now()
        rows_json = json.dumps(
            [_total_sales_row_to_dict(row) for row in rows],
            ensure_ascii=False,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_total_sales_rows_cache (
                    cache_key,
                    date_from,
                    date_to,
                    rows_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    date_from = excluded.date_from,
                    date_to = excluded.date_to,
                    rows_json = excluded.rows_json,
                    updated_at = excluded.updated_at
                """,
                (cache_key, date_from, date_to, rows_json, now, now),
            )

    def _upsert_report_job(self, job: OzonReportJobRecord) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ozon_report_jobs (
                    job_id,
                    report_type,
                    campaign_id,
                    date_from,
                    date_to,
                    unit_economy_signature,
                    cache_key,
                    status,
                    phase,
                    progress_percent,
                    message,
                    error,
                    result_source,
                    created_at,
                    started_at,
                    finished_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    phase = excluded.phase,
                    progress_percent = excluded.progress_percent,
                    message = excluded.message,
                    error = excluded.error,
                    result_source = excluded.result_source,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    updated_at = excluded.updated_at
                """,
                (
                    job.job_id,
                    job.report_type,
                    job.campaign_id,
                    job.date_from,
                    job.date_to,
                    job.unit_economy_signature,
                    job.cache_key,
                    job.status,
                    job.phase,
                    job.progress_percent,
                    job.message,
                    job.error,
                    job.result_source,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    now,
                ),
            )

    def _get_report_job(self, job_id: str) -> OzonReportJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM ozon_report_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

        return _row_to_job_record(row)

    def _find_active_report_job(
        self,
        report_type: str,
        campaign_id: str,
        date_from: str,
        date_to: str,
        unit_economy_signature: str,
    ) -> OzonReportJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM ozon_report_jobs
                WHERE report_type = ?
                    AND campaign_id = ?
                    AND date_from = ?
                    AND date_to = ?
                    AND unit_economy_signature = ?
                    AND status IN ('queued', 'running')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (
                    report_type,
                    campaign_id,
                    date_from,
                    date_to,
                    unit_economy_signature,
                ),
            ).fetchone()

        return _row_to_job_record(row)

    def _cancel_active_report_jobs(
        self,
        report_type: str,
        except_cache_key: str,
        message: str,
    ) -> list[str]:
        now = _utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id
                FROM ozon_report_jobs
                WHERE report_type = ?
                    AND cache_key != ?
                    AND status IN ('queued', 'running')
                """,
                (report_type, except_cache_key),
            ).fetchall()
            job_ids = [str(row["job_id"]) for row in rows]
            if job_ids:
                connection.execute(
                    """
                    UPDATE ozon_report_jobs
                    SET status = 'cancelled',
                        phase = 'cancelled',
                        progress_percent = 100,
                        message = ?,
                        error = NULL,
                        finished_at = COALESCE(finished_at, ?),
                        updated_at = ?
                    WHERE report_type = ?
                        AND cache_key != ?
                        AND status IN ('queued', 'running')
                    """,
                    (message, now, now, report_type, except_cache_key),
                )

        return job_ids


def _select_report_id(connection: sqlite3.Connection, report_uuid: str) -> int:
    row = connection.execute(
        "SELECT id FROM ozon_ad_reports WHERE report_uuid = ?",
        (report_uuid,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Ozon ad report {report_uuid} was not saved")

    return int(row["id"])


def _unit_version_values(
    unit_economy_version: UnitEconomyWorkbookVersion | None,
) -> tuple[str | None, str | None, str | None, int | None]:
    if unit_economy_version is None:
        return None, None, None, None

    return (
        unit_economy_version.path,
        unit_economy_version.version_id,
        unit_economy_version.modified_at,
        unit_economy_version.size_bytes,
    )


def _row_to_status(row: sqlite3.Row | None) -> OzonStatisticsReportStatus | None:
    if row is None:
        return None

    return OzonStatisticsReportStatus(
        campaign_id=row["campaign_id"],
        report_uuid=row["report_uuid"],
        state=row["state"],
        link=row["link"],
        created_at=row["ozon_created_at"],
        updated_at=row["ozon_updated_at"],
    )


def _row_to_job_record(row: sqlite3.Row | None) -> OzonReportJobRecord | None:
    if row is None:
        return None

    return OzonReportJobRecord(
        job_id=row["job_id"],
        report_type=row["report_type"],
        campaign_id=row["campaign_id"],
        date_from=row["date_from"],
        date_to=row["date_to"],
        unit_economy_signature=row["unit_economy_signature"],
        cache_key=row["cache_key"],
        status=row["status"],
        phase=row["phase"],
        progress_percent=int(row["progress_percent"]),
        message=row["message"],
        error=row["error"],
        result_source=row["result_source"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _total_sales_rows_cache_key(date_from: str, date_to: str) -> str:
    return f"seller-total-sales:{date_from}:{date_to}"


def _total_sales_row_to_dict(row: OzonTotalSalesReportRow) -> dict[str, object]:
    return {
        "offer_id": row.offer_id,
        "sku": row.sku,
        "title": row.title,
        "ordered_amount_with_vat": row.ordered_amount_with_vat,
        "orders": row.orders,
        "seller_product_id": row.seller_product_id,
        "promotions": [
            promotion.model_dump()
            for promotion in (row.promotions or [])
        ],
    }


def _total_sales_row_from_dict(raw: object) -> OzonTotalSalesReportRow:
    if not isinstance(raw, dict):
        raise ValueError("Cached Ozon total sales row is invalid")

    raw_promotions = raw.get("promotions")
    promotions = (
        [
            OzonPromotionInfo.model_validate(promotion)
            for promotion in raw_promotions
            if isinstance(promotion, dict)
        ]
        if isinstance(raw_promotions, list)
        else []
    )
    return OzonTotalSalesReportRow(
        offer_id=_optional_text(raw.get("offer_id")),
        sku=_optional_text(raw.get("sku")),
        title=_optional_text(raw.get("title")),
        ordered_amount_with_vat=float(raw.get("ordered_amount_with_vat") or 0),
        orders=int(raw.get("orders") or 0),
        seller_product_id=_optional_text(raw.get("seller_product_id")),
        promotions=promotions,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
