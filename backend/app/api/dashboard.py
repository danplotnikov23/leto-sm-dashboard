from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_ozon_dashboard_service
from app.schemas.dashboard import OzonDashboardPeriod, OzonDashboardSalesResponse
from app.services.ozon_dashboard_service import OzonDashboardService
from app.services.ozon_errors import OzonApiError, OzonConfigurationError


router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/ozon-sales", response_model=OzonDashboardSalesResponse)
async def get_ozon_sales_dashboard(
    service: Annotated[
        OzonDashboardService,
        Depends(get_ozon_dashboard_service),
    ],
    period: OzonDashboardPeriod = "28d",
    force_refresh: bool = False,
) -> OzonDashboardSalesResponse:
    try:
        return await service.get_sales_dashboard(
            period=period,
            force_refresh=force_refresh,
        )
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
