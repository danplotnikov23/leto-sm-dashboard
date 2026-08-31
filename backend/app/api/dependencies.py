from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.services.marketplace_tools_service import MarketplaceToolsService
from app.services.ozon_accruals_service import OzonAccrualsService
from app.services.ozon_ad_report_repository import OzonAdReportRepository
from app.services.ozon_ads_service import OzonAdsService
from app.services.ozon_dashboard_service import OzonDashboardService
from app.services.ozon_price_snapshot_service import OzonPriceSnapshotService
from app.services.ozon_report_job_service import OzonReportJobService
from app.services.ozon_seller_client import OzonSellerClient
from app.services.price_update_service import PriceUpdateService
from app.services.unit_economy_index_service import UnitEconomyIndexService
from app.services.unit_economy_service import UnitEconomyService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_unit_economy_service(request: Request) -> UnitEconomyService:
    return request.app.state.unit_economy_service


def get_unit_economy_index_service(request: Request) -> UnitEconomyIndexService:
    return request.app.state.unit_economy_index_service


def get_price_update_service(
    unit_economy_index_service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
) -> PriceUpdateService:
    return PriceUpdateService(unit_economy_index_service)


def get_ozon_accruals_service(request: Request) -> OzonAccrualsService:
    return request.app.state.ozon_accruals_service


def get_ozon_ad_report_repository(request: Request) -> OzonAdReportRepository:
    return request.app.state.ozon_ad_report_repository


def get_ozon_report_job_service(request: Request) -> OzonReportJobService:
    return request.app.state.ozon_report_job_service


def get_ozon_price_snapshot_service(request: Request) -> OzonPriceSnapshotService:
    return request.app.state.ozon_price_snapshot_service


def get_ozon_dashboard_service(request: Request) -> OzonDashboardService:
    return request.app.state.ozon_dashboard_service


def get_ozon_ads_service(
    settings: Annotated[Settings, Depends(get_app_settings)],
    unit_economy_index_service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
    ozon_ad_report_repository: Annotated[
        OzonAdReportRepository,
        Depends(get_ozon_ad_report_repository),
    ],
) -> OzonAdsService:
    return OzonAdsService(
        settings,
        unit_economy_index_service,
        ozon_ad_report_repository,
    )


def get_ozon_seller_client(request: Request) -> OzonSellerClient:
    return OzonSellerClient(request.app.state.settings)


def get_marketplace_tools_service(request: Request) -> MarketplaceToolsService:
    return request.app.state.marketplace_tools_service
