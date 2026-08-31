import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.schemas.unit_economy_index import UnitEconomyProduct
from app.services.ozon_ad_attribution_calculator import (
    OzonAdAttributionCalculator,
    ResolvedAttributionProduct,
)
from app.services.ozon_ads_service import _filter_promotion_report_by_campaign
from app.services.ozon_errors import OzonApiError
from app.services.ozon_promotion_analytics_parser import (
    OzonPromotionAnalyticsParser,
    PromotionAnalyticsReport,
    PromotionStatisticsRow,
    PromotionUnionRow,
)
from app.services.ozon_seller_client import OzonSellerClient


REAL_PROMOTION_REPORT = Path(
    "/Users/daniilplotnikov/Downloads/Аналитика продвижения_30.07.2026.xlsx"
)


def _unit_product(
    offer_id: str,
    sku: str,
    expense_with_ozon_commission: float | None,
) -> UnitEconomyProduct:
    return UnitEconomyProduct(
        row_number=4,
        offer_id=offer_id,
        ozon_sku=sku,
        title=f"Товар {offer_id}",
        sale_schema="realFBS",
        price_with_vat=None,
        price_without_vat=None,
        cost_without_vat=None,
        ozon_commission=None,
        ad_cost=None,
        expense_cost=None,
        expense_with_ozon_commission=expense_with_ozon_commission,
        profit_before_tax=None,
        tax=None,
        net_profit=None,
        profitability=None,
    )


def _resolved_product(
    sku: str,
    offer_id: str,
    expense_with_ozon_commission: float | None,
) -> ResolvedAttributionProduct:
    unit = _unit_product(offer_id, sku, expense_with_ozon_commission)
    return ResolvedAttributionProduct(
        sku=sku,
        offer_id=offer_id,
        title=unit.title,
        unit_economy=unit,
        mapping_source="seller_api+unit_economy",
        status=(
            "OK"
            if expense_with_ozon_commission is not None
            else "UNIT_COST_NOT_FOUND"
        ),
    )


def _statistics(
    *,
    spend_with_vat: str = "1220",
    direct_revenue_with_vat: str = "12200",
    direct_orders: int = 2,
    model_revenue_with_vat: str = "6100",
    model_orders: int = 1,
) -> PromotionStatisticsRow:
    return PromotionStatisticsRow(
        promoted_sku="100",
        title="Продвигаемый товар",
        campaign_id="42",
        instrument="Оплата за клик",
        placement="Поиск",
        spend_with_vat=Decimal(spend_with_vat),
        direct_revenue_with_vat=Decimal(direct_revenue_with_vat),
        direct_orders=direct_orders,
        model_revenue_with_vat=Decimal(model_revenue_with_vat),
        model_orders=model_orders,
    )


def _union(
    *,
    revenue_with_vat: str = "6100",
    orders: int = 1,
) -> PromotionUnionRow:
    return PromotionUnionRow(
        promoted_sku="100",
        promoted_title="Продвигаемый товар",
        campaign_id="42",
        instrument="Оплата за клик",
        placement="Поиск",
        purchased_sku="200",
        purchased_title="Купленный товар",
        revenue_with_vat=Decimal(revenue_with_vat),
        orders=orders,
    )


def _calculate(
    report: PromotionAnalyticsReport,
    products: dict[str, ResolvedAttributionProduct],
):
    return OzonAdAttributionCalculator().calculate_import(
        campaign_id="ALL",
        date_from="2026-07-01",
        date_to="2026-07-30",
        report=report,
        products_by_sku=products,
        unit_economy_version="2026-06-15",
        unit_economy_warning=None,
    )


def test_models_use_purchased_sku_cost_and_spend_is_charged_once() -> None:
    response = _calculate(
        PromotionAnalyticsReport(
            statistics=[_statistics()],
            union=[_union()],
        ),
        {
            "100": _resolved_product("100", "A-100", 1000),
            "200": _resolved_product("200", "A-200", 2000),
        },
    )

    row = response.rows[0]
    assert row.direct.orders == 2
    assert row.direct.revenue_without_vat == pytest.approx(10000)
    assert row.direct.total_cost == pytest.approx(2000)
    assert row.direct.tax == pytest.approx(1760)
    assert row.direct.net_profit == pytest.approx(5240)

    assert row.with_models.orders == 3
    assert row.with_models.revenue_without_vat == pytest.approx(15000)
    assert row.with_models.total_cost == pytest.approx(4000)
    assert row.with_models.tax == pytest.approx(2420)
    assert row.with_models.profit_before_ads == pytest.approx(8580)
    assert row.with_models.spend_without_vat == pytest.approx(1000)
    assert row.with_models.net_profit == pytest.approx(7580)
    assert row.with_models.romi_percent == pytest.approx(758)
    assert row.status == "OK"

    model_child = next(
        child for child in row.children if child.sale_type == "model"
    )
    assert model_child.purchased_sku == "200"
    assert model_child.unit_cost == pytest.approx(2000)


def test_missing_model_cost_marks_partial_coverage_without_zero_cost() -> None:
    response = _calculate(
        PromotionAnalyticsReport(
            statistics=[_statistics()],
            union=[_union()],
        ),
        {
            "100": _resolved_product("100", "A-100", 1000),
            "200": _resolved_product("200", "A-200", None),
        },
    )

    row = response.rows[0]
    assert row.status == "UNIT_COST_NOT_FOUND"
    assert row.with_models.complete is False
    assert row.with_models.coverage_orders_percent == pytest.approx(66.67)
    assert row.with_models.coverage_percent == pytest.approx(66.67)
    assert row.with_models.total_cost == pytest.approx(2000)
    assert row.with_models.net_profit == pytest.approx(5240)
    assert any("не заполнен" in issue for issue in row.issues)


def test_spend_without_sales_is_a_valid_negative_result() -> None:
    response = _calculate(
        PromotionAnalyticsReport(
            statistics=[
                _statistics(
                    spend_with_vat="1220",
                    direct_revenue_with_vat="0",
                    direct_orders=0,
                    model_revenue_with_vat="0",
                    model_orders=0,
                )
            ],
            union=[],
        ),
        {"100": _resolved_product("100", "A-100", 1000)},
    )

    row = response.rows[0]
    assert row.status == "SPEND_WITHOUT_SALES"
    assert row.with_models.net_profit == pytest.approx(-1000)
    assert row.with_models.drr_percent is None
    assert row.with_models.romi_percent == pytest.approx(-100)


def test_union_mismatch_is_visible_and_blocks_ok_status() -> None:
    response = _calculate(
        PromotionAnalyticsReport(
            statistics=[_statistics(model_orders=2)],
            union=[_union(orders=1)],
        ),
        {
            "100": _resolved_product("100", "A-100", 1000),
            "200": _resolved_product("200", "A-200", 2000),
        },
    )

    assert response.rows[0].status == "UNION_QUANTITY_MISMATCH"
    assert any(
        issue.startswith("UNION_QUANTITY_MISMATCH")
        for issue in response.rows[0].issues
    )


def test_selected_campaign_filters_statistics_and_union_before_mapping() -> None:
    report = PromotionAnalyticsReport(
        statistics=[
            _statistics(),
            PromotionStatisticsRow(
                promoted_sku="300",
                title="Другой товар",
                campaign_id="84",
                instrument="Оплата за клик",
                placement="Поиск",
                spend_with_vat=Decimal("100"),
                direct_revenue_with_vat=Decimal("1000"),
                direct_orders=1,
                model_revenue_with_vat=Decimal("500"),
                model_orders=1,
            ),
        ],
        union=[
            _union(),
            PromotionUnionRow(
                promoted_sku="300",
                promoted_title="Другой товар",
                campaign_id="84",
                instrument="Оплата за клик",
                placement="Поиск",
                purchased_sku="400",
                purchased_title="Другая модель",
                revenue_with_vat=Decimal("500"),
                orders=1,
            ),
        ],
    )

    selected = _filter_promotion_report_by_campaign(report, "42")

    assert {row.promoted_sku for row in selected.statistics} == {"100"}
    assert {row.purchased_sku for row in selected.union} == {"200"}


def test_seller_sku_lookup_keeps_valid_products_when_one_sku_fails() -> None:
    class StubSellerClient(OzonSellerClient):
        def __init__(self) -> None:
            pass

        async def request(
            self,
            path: str,
            payload: dict[str, object] | None = None,
            timeout_seconds: float | None = None,
            retry_count: int | None = None,
            method: str = "POST",
        ) -> dict[str, object]:
            del path, timeout_seconds, retry_count, method
            requested_skus = list((payload or {}).get("sku", []))
            if "BAD" in requested_skus:
                raise OzonApiError("invalid sku")
            return {
                "items": [
                    {"sku": int(sku), "offer_id": f"A-{sku}"}
                    for sku in requested_skus
                ]
            }

    products = asyncio.run(
        StubSellerClient().get_products_by_sku(
            ["100", "BAD", "200", "100"]
        )
    )

    assert set(products) == {"100", "200"}


@pytest.mark.skipif(
    not REAL_PROMOTION_REPORT.exists(),
    reason="Контрольный XLSX Ozon не найден на локальном компьютере",
)
def test_real_promotion_report_statistics_and_union_totals_match() -> None:
    parser = OzonPromotionAnalyticsParser()
    report = parser.parse(
        REAL_PROMOTION_REPORT.name,
        REAL_PROMOTION_REPORT.read_bytes(),
    )

    assert len(report.statistics) == 76
    assert len(report.union) == 177
    assert len({row.campaign_id for row in report.statistics}) == 62
    assert len({row.promoted_sku for row in report.statistics}) == 72
    assert sum(
        row.spend_with_vat for row in report.statistics
    ) == Decimal("665344.223893")
    assert sum(
        row.direct_revenue_with_vat for row in report.statistics
    ) == Decimal("4517184")
    assert sum(row.direct_orders for row in report.statistics) == 166
    assert sum(
        row.model_revenue_with_vat for row in report.statistics
    ) == Decimal("3352704")
    assert sum(row.model_orders for row in report.statistics) == 230
    assert sum(
        row.revenue_with_vat for row in report.union
    ) == Decimal("3352704")
    assert sum(row.orders for row in report.union) == 230
