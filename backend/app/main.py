import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from app.api.dashboard import router as dashboard_router
from app.api.marketplace_tools import router as marketplace_tools_router
from app.api.ozon_accruals import router as ozon_accruals_router
from app.api.ozon import router as ozon_router
from app.api.ozon_promotions import router as ozon_promotions_router
from app.api.price_update import router as price_update_router
from app.api.unit_economy_index import router as unit_economy_index_router
from app.api.unit_economy import router as unit_economy_router
from app.core.config import Settings, get_settings
from app.services.daily_profit_scheduler import DailyProfitScheduler
from app.services.order_profit_scheduler import OrderProfitScheduler
from app.services.ozon_accruals_service import OzonAccrualsService
from app.services.ozon_ad_report_repository import OzonAdReportRepository
from app.services.ozon_ads_service import OzonAdsService
from app.services.ozon_dashboard_service import OzonDashboardService
from app.services.ozon_seller_client import OzonSellerClient
from app.services.marketplace_tools_service import MarketplaceToolsService
from app.services.ozon_price_snapshot_service import OzonPriceSnapshotService
from app.services.ozon_report_job_service import OzonReportJobService
from app.services.unit_economy_index_service import UnitEconomyIndexService
from app.services.unit_economy_service import UnitEconomyService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.unit_economy_service = UnitEconomyService(upload_dir=settings.upload_dir)
    app.state.unit_economy_index_service = UnitEconomyIndexService(
        workbook_path=settings.unit_economy_workbook_path,
        workbook_versions=settings.unit_economy_workbook_versions,
        versions_dir=settings.unit_economy_versions_dir,
    )
    app.state.marketplace_tools_service = MarketplaceToolsService(
        artifacts_dir=settings.upload_dir / "marketplace-tools",
    )
    app.state.ozon_accruals_service = OzonAccrualsService(
        report_path=settings.ozon_accruals_report_path
    )
    app.state.ozon_ad_report_repository = OzonAdReportRepository(
        database_path=settings.database_path
    )
    await app.state.ozon_ad_report_repository.initialize()
    app.state.ozon_price_snapshot_service = OzonPriceSnapshotService(settings)
    await app.state.ozon_price_snapshot_service.initialize()
    app.state.ozon_dashboard_service = OzonDashboardService(
        OzonSellerClient(settings)
    )
    app.state.ozon_report_job_service = OzonReportJobService(
        settings,
        app.state.unit_economy_index_service,
        app.state.ozon_ad_report_repository,
    )
    daily_profit_ads_service = OzonAdsService(
        settings,
        app.state.unit_economy_index_service,
        app.state.ozon_ad_report_repository,
    )
    app.state.daily_profit_scheduler = DailyProfitScheduler(
        daily_profit_ads_service,
        app.state.ozon_ad_report_repository,
    )
    app.state.daily_profit_scheduler.start()
    app.state.order_profit_scheduler = OrderProfitScheduler(daily_profit_ads_service)
    app.state.order_profit_scheduler.start()
    try:
        yield
    finally:
        await app.state.order_profit_scheduler.stop()
        await app.state.daily_profit_scheduler.stop()
        await app.state.ozon_report_job_service.shutdown()


app = FastAPI(
    title="Leto SM Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(unit_economy_router)
app.include_router(unit_economy_index_router)
app.include_router(ozon_router, prefix="/api/ozon", tags=["Ozon"])
app.include_router(ozon_promotions_router)
app.include_router(ozon_accruals_router)
app.include_router(marketplace_tools_router)
app.include_router(price_update_router)
app.include_router(dashboard_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "Leto SM Dashboard backend is running",
    }
