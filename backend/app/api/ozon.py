from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.api.dependencies import (
    get_app_settings,
    get_ozon_ads_service,
    get_ozon_price_snapshot_service,
    get_ozon_report_job_service,
    get_ozon_seller_client,
)
from app.core.config import Settings
from app.schemas.ozon import (
    OzonCampaignProductsResponse,
    OzonCampaignsResponse,
    OzonCampaignEfficiencyResponse,
    OzonHealthResponse,
    OzonIntegrationStatus,
    OzonReportJobCreateRequest,
    OzonReportJobResponse,
    OzonSalesAnalyticsResponse,
    OzonSalesForecastRequest,
    OzonSalesForecastResponse,
    OzonSkuDailyProfitResponse,
    OzonSkuEfficiencyResponse,
    OzonStatisticsReportStatus,
    OzonStoredReportsResponse,
)
from app.schemas.ozon_price import OzonPriceSnapshotResponse
from app.schemas.ozon_ad_attribution import (
    OzonAdAttributionResponse,
    OzonPromotionAnalyticsImportsResponse,
)
from app.schemas.ozon_daily_profit import OzonDailyProfitRegistryResponse
from app.schemas.ozon_order_lookup import (
    OzonAdSpendForDateResponse,
    OzonOrderDeliveryActualCostInput,
    OzonOrderLookupResponse,
    OzonTodayOrdersSummary,
)
from app.schemas.ozon_product_sales import (
    OzonProductSalesImportsResponse,
    OzonProductSalesResponse,
)
from app.services.ozon_ads_service import OzonAdsService
from app.services.ozon_errors import (
    OzonApiError,
    OzonConfigurationError,
    OzonReportNotReadyError,
)
from app.services.ozon_period_validation import validate_ozon_report_period
from app.services.ozon_report_job_service import OzonReportJobService
from app.services.ozon_price_snapshot_service import OzonPriceSnapshotService
from app.services.ozon_seller_client import OzonSellerClient

router = APIRouter()


@router.get("/status", response_model=OzonIntegrationStatus)
def get_status(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> OzonIntegrationStatus:
    return OzonIntegrationStatus(
        seller_credentials_configured=settings.seller_credentials_configured,
        performance_credentials_configured=settings.performance_credentials_configured,
    )


@router.get("/health", response_model=OzonHealthResponse)
async def check_health(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonHealthResponse:
    seller_status = "ok"
    performance_status = "ok"

    try:
        await service.check_seller_connection()
    except (OzonConfigurationError, OzonApiError) as exc:
        seller_status = str(exc)

    try:
        await service.check_performance_connection()
    except (OzonConfigurationError, OzonApiError) as exc:
        performance_status = str(exc)

    status = "ok" if seller_status == "ok" and performance_status == "ok" else "error"
    return OzonHealthResponse(
        status=status,
        seller=seller_status,
        performance=performance_status,
    )


@router.get("/prices/current", response_model=OzonPriceSnapshotResponse)
async def get_current_price_snapshots(
    service: Annotated[
        OzonPriceSnapshotService,
        Depends(get_ozon_price_snapshot_service),
    ],
    offer_ids: str,
) -> OzonPriceSnapshotResponse:
    try:
        snapshots = await service.fetch_current_snapshots(offer_ids.split(","))
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return OzonPriceSnapshotResponse(items=snapshots)


@router.get("/campaigns", response_model=OzonCampaignsResponse)
async def get_campaigns(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonCampaignsResponse:
    try:
        campaigns = await service.get_campaigns()
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return OzonCampaignsResponse(campaigns=campaigns)


@router.get("/campaigns/period", response_model=OzonCampaignsResponse)
async def get_campaigns_for_period(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str,
    date_to: str,
) -> OzonCampaignsResponse:
    try:
        validate_ozon_report_period(date_from, date_to)
        campaigns = await service.get_campaigns_for_period(date_from, date_to)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return OzonCampaignsResponse(campaigns=campaigns)


@router.get(
    "/campaigns/{campaign_id}/products",
    response_model=OzonCampaignProductsResponse,
)
async def get_campaign_products(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
) -> OzonCampaignProductsResponse:
    try:
        products = await service.get_campaign_products(campaign_id)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc

    return OzonCampaignProductsResponse(products=products)


@router.get(
    "/campaigns/{campaign_id}/efficiency",
    response_model=OzonCampaignEfficiencyResponse,
)
async def get_campaign_efficiency(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonCampaignEfficiencyResponse:
    try:
        validate_ozon_report_period(date_from, date_to)
        return await service.get_campaign_efficiency(campaign_id, date_from, date_to)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/sku-efficiency-reports",
    response_model=OzonStoredReportsResponse,
)
async def list_saved_sku_efficiency_reports(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    limit: int = 50,
) -> OzonStoredReportsResponse:
    reports = await service.list_saved_sku_efficiency_reports(limit)
    return OzonStoredReportsResponse(reports=reports)


@router.get(
    "/sku-efficiency-reports/{report_uuid}/result",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_saved_sku_efficiency_report_result(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    report_uuid: str,
) -> OzonSkuEfficiencyResponse:
    result = await service.get_saved_sku_efficiency_report_result(report_uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="Saved Ozon report result not found")

    return result


@router.get(
    "/sales-analytics",
    response_model=OzonSalesAnalyticsResponse,
)
async def get_sales_analytics(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str,
    date_to: str,
) -> OzonSalesAnalyticsResponse:
    try:
        validate_ozon_report_period(date_from, date_to)
        return await service.get_sales_analytics(date_from, date_to)
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/sku-daily-profit",
    response_model=OzonSkuDailyProfitResponse,
)
async def get_sku_daily_profit(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str,
    date_to: str,
    sku: str | None = None,
    offer_id: str | None = None,
    ad_spend_without_vat: float = 0,
    profit_tax_rate: float = 0.22,
) -> OzonSkuDailyProfitResponse:
    try:
        validate_ozon_report_period(date_from, date_to)
        return await service.get_sku_daily_profit(
            date_from=date_from,
            date_to=date_to,
            sku=sku,
            offer_id=offer_id,
            ad_spend_without_vat=ad_spend_without_vat,
            profit_tax_rate=profit_tax_rate,
        )
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/sales-forecast",
    response_model=OzonSalesForecastResponse,
)
async def get_sales_forecast(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    payload: OzonSalesForecastRequest,
) -> OzonSalesForecastResponse:
    try:
        validate_ozon_report_period(payload.date_from, payload.date_to)
        return await service.get_sales_forecast(payload)
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/sku-efficiency",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_campaign_sku_efficiency(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.get_campaign_sku_efficiency(campaign_id, date_from, date_to)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/sku-efficiency-composite",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_campaign_sku_efficiency_composite(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.get_campaign_sku_efficiency_composite(
            campaign_id,
            date_from,
            date_to,
        )
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/ad-attribution",
    response_model=OzonAdAttributionResponse,
)
async def get_campaign_ad_attribution(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonAdAttributionResponse:
    try:
        return await service.get_ad_attribution_from_api(
            campaign_id,
            date_from,
            date_to,
        )
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc


@router.post(
    "/campaigns/{campaign_id}/sku-efficiency-reports/import",
    response_model=OzonSkuEfficiencyResponse,
)
async def import_campaign_sku_efficiency_report(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
    file: UploadFile = File(...),
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.import_sku_efficiency_report(
            campaign_id,
            date_from,
            date_to,
            file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/campaigns/{campaign_id}/ad-attribution/import",
    response_model=OzonAdAttributionResponse,
)
async def import_campaign_ad_attribution(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
    file: UploadFile = File(...),
) -> OzonAdAttributionResponse:
    try:
        return await service.import_ad_attribution_report(
            campaign_id,
            date_from,
            date_to,
            file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/promotion-analytics-imports",
    response_model=OzonPromotionAnalyticsImportsResponse,
)
async def list_promotion_analytics_imports(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonPromotionAnalyticsImportsResponse:
    imports = await service.list_promotion_analytics_imports()
    return OzonPromotionAnalyticsImportsResponse(imports=imports)


@router.get(
    "/promotion-analytics-imports/{import_id}",
    response_model=OzonAdAttributionResponse,
)
async def get_promotion_analytics_import(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    import_id: int,
) -> OzonAdAttributionResponse:
    result = await service.get_promotion_analytics_import(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Сохранённый отчёт не найден")
    return result


@router.post(
    "/product-sales/import",
    response_model=OzonProductSalesResponse,
)
async def import_product_sales_report(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    file: UploadFile = File(...),
) -> OzonProductSalesResponse:
    try:
        return await service.import_product_sales_report(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/product-sales/imports",
    response_model=OzonProductSalesImportsResponse,
)
async def list_product_sales_imports(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonProductSalesImportsResponse:
    imports = await service.list_product_sales_imports()
    return OzonProductSalesImportsResponse(imports=imports)


@router.get(
    "/product-sales",
    response_model=OzonProductSalesResponse,
)
async def get_product_sales_profit(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str,
    date_to: str,
) -> OzonProductSalesResponse:
    try:
        return await service.get_product_sales_profit(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/daily-profit",
    response_model=OzonDailyProfitRegistryResponse,
)
async def list_daily_profit_snapshots(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonDailyProfitRegistryResponse:
    snapshots = await service.list_daily_profit_snapshots()
    return OzonDailyProfitRegistryResponse(snapshots=snapshots)


@router.post(
    "/daily-profit/run",
    response_model=OzonDailyProfitRegistryResponse,
)
async def run_daily_profit_snapshot(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
    run_type: str = "final",
) -> OzonDailyProfitRegistryResponse:
    try:
        await service.compute_daily_profit_snapshot(date, run_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    snapshots = await service.list_daily_profit_snapshots()
    return OzonDailyProfitRegistryResponse(snapshots=snapshots)


@router.delete(
    "/daily-profit",
    response_model=OzonDailyProfitRegistryResponse,
)
async def delete_daily_profit_snapshot(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
    run_type: str,
) -> OzonDailyProfitRegistryResponse:
    await service.delete_daily_profit_snapshot(date, run_type)
    snapshots = await service.list_daily_profit_snapshots()
    return OzonDailyProfitRegistryResponse(snapshots=snapshots)


@router.get("/daily-profit/export.xlsx")
async def export_daily_profit_xlsx(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str | None = None,
    date_to: str | None = None,
) -> Response:
    try:
        content = await service.export_daily_profit_xlsx(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="leto_sm_daily_profit_registry.xlsx"'
            )
        },
    )


@router.get(
    "/orders/today",
    response_model=list[OzonOrderLookupResponse],
)
async def list_today_orders(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> list[OzonOrderLookupResponse]:
    return await service.list_today_orders_profit()


@router.post(
    "/orders/today/refresh",
    response_model=list[OzonOrderLookupResponse],
)
async def refresh_today_orders(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> list[OzonOrderLookupResponse]:
    try:
        return await service.refresh_today_orders_and_ad_spend()
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/orders/today/summary",
    response_model=OzonTodayOrdersSummary,
)
async def get_today_orders_summary(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonTodayOrdersSummary:
    return await service.get_today_orders_summary()


@router.post("/orders/today/refresh-ad-spend")
async def refresh_today_ad_spend(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> dict[str, str]:
    # Fire-and-forget - can take minutes (Ozon's per-campaign report fallback),
    # so this only kicks it off; the frontend polls /orders/today/summary
    # afterwards to notice the fresh number once it lands.
    service.trigger_today_ad_spend_refresh()
    return {"status": "started"}


@router.get(
    "/orders/by-date",
    response_model=list[OzonOrderLookupResponse],
)
async def list_orders_by_date(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
) -> list[OzonOrderLookupResponse]:
    try:
        return await service.list_orders_profit_for_date(date)
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orders/by-date/export.xlsx")
async def export_orders_by_date_xlsx(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
) -> Response:
    try:
        content = await service.export_orders_for_date_xlsx(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="leto_sm_orders_{date}.xlsx"'
        },
    )


@router.get("/ad-spend", response_model=OzonAdSpendForDateResponse)
async def get_ad_spend_for_date(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
) -> OzonAdSpendForDateResponse:
    ad_spend, warning = await service.get_ad_spend_for_date(date)
    return OzonAdSpendForDateResponse(date=date, ad_spend_without_vat=ad_spend, warning=warning)


@router.post(
    "/orders/by-date/refresh",
    response_model=list[OzonOrderLookupResponse],
)
async def refresh_orders_by_date(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date: str,
) -> list[OzonOrderLookupResponse]:
    # Unlike GET /orders/by-date, this always recomputes from scratch and
    # overwrites the saved snapshots - needed after a юнитка version gets
    # corrected/uploaded, so past dates pick up the new numbers instead of
    # forever serving whatever was cached the first time that date was viewed.
    try:
        return await service.compute_orders_profit_for_date(date)
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/orders/export.xlsx")
async def export_orders_xlsx(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    date_from: str,
    date_to: str,
) -> Response:
    try:
        content = await service.export_orders_xlsx(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="leto_sm_orders_{date_from}_{date_to}.xlsx"'
            )
        },
    )


@router.get(
    "/orders/{posting_number}",
    response_model=OzonOrderLookupResponse,
)
async def get_order_profit(
    posting_number: str,
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonOrderLookupResponse:
    try:
        return await service.compute_order_profit(posting_number)
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/orders/{posting_number}/delivery-actual-cost",
    response_model=OzonOrderLookupResponse,
)
async def save_order_delivery_actual_cost(
    posting_number: str,
    payload: OzonOrderDeliveryActualCostInput,
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
) -> OzonOrderLookupResponse:
    try:
        return await service.save_delivery_actual_cost(posting_number, payload.actual_cost)
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/campaigns/{campaign_id}/total-sales-report/import",
    response_model=OzonSkuEfficiencyResponse,
)
async def import_campaign_total_sales_report(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
    file: UploadFile = File(...),
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.import_total_sales_report(
            campaign_id,
            date_from,
            date_to,
            file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/total-sales-report/api",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_campaign_total_sales_report_from_api(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.get_total_sales_report_from_api(
            campaign_id,
            date_from,
            date_to,
        )
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc


@router.post(
    "/total-sales-report-jobs",
    response_model=OzonReportJobResponse,
)
async def create_total_sales_report_job(
    job_service: Annotated[
        OzonReportJobService,
        Depends(get_ozon_report_job_service),
    ],
    payload: OzonReportJobCreateRequest,
) -> OzonReportJobResponse:
    try:
        return await job_service.create_total_sales_report_job(
            payload.campaign_id,
            payload.date_from,
            payload.date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/total-sales-report-jobs/{job_id}",
    response_model=OzonReportJobResponse,
)
async def get_total_sales_report_job(
    job_service: Annotated[
        OzonReportJobService,
        Depends(get_ozon_report_job_service),
    ],
    job_id: str,
) -> OzonReportJobResponse:
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ozon report job not found")

    return job


@router.get(
    "/total-sales-report-jobs/{job_id}/result",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_total_sales_report_job_result(
    job_service: Annotated[
        OzonReportJobService,
        Depends(get_ozon_report_job_service),
    ],
    job_id: str,
) -> OzonSkuEfficiencyResponse:
    result = await job_service.get_job_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ozon report job result not found")

    return result


@router.post(
    "/campaigns/{campaign_id}/sku-efficiency-reports",
    response_model=OzonStatisticsReportStatus,
)
async def create_campaign_sku_efficiency_report(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    date_from: str,
    date_to: str,
) -> OzonStatisticsReportStatus:
    try:
        return await service.create_sku_efficiency_report(campaign_id, date_from, date_to)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/sku-efficiency-reports/{report_uuid}",
    response_model=OzonStatisticsReportStatus,
)
async def get_campaign_sku_efficiency_report_status(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    report_uuid: str,
) -> OzonStatisticsReportStatus:
    try:
        return await service.get_statistics_report_status(campaign_id, report_uuid)
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/campaigns/{campaign_id}/sku-efficiency-reports/{report_uuid}/result",
    response_model=OzonSkuEfficiencyResponse,
)
async def get_campaign_sku_efficiency_report_result(
    service: Annotated[OzonAdsService, Depends(get_ozon_ads_service)],
    campaign_id: str,
    report_uuid: str,
    date_from: str,
    date_to: str,
) -> OzonSkuEfficiencyResponse:
    try:
        return await service.get_campaign_sku_efficiency(
            campaign_id,
            date_from,
            date_to,
            report_uuid=report_uuid,
        )
    except OzonReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"report_uuid": exc.report_uuid, "state": exc.state},
        ) from exc
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/stocks")
async def get_stocks(
    client: Annotated[OzonSellerClient, Depends(get_ozon_seller_client)],
) -> list[dict[str, object]]:
    try:
        return await client.get_stocks()
    except OzonConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OzonApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
