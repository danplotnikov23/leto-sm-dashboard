from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.schemas.ozon import OzonSkuEfficiencyResponse
from app.schemas.ozon_ad_attribution import (
    OzonAdAttributionChild,
    OzonAdAttributionMetrics,
    OzonAdAttributionResponse,
    OzonAdAttributionRow,
)
from app.schemas.unit_economy_index import UnitEconomyProduct
from app.services.financial_calculator import money, profit_tax, without_vat
from app.services.ozon_promotion_analytics_parser import (
    PromotionAnalyticsReport,
    PromotionStatisticsRow,
    PromotionUnionRow,
)


@dataclass(frozen=True, slots=True)
class _GroupKey:
    campaign_id: str
    promoted_sku: str


@dataclass(frozen=True, slots=True)
class ResolvedAttributionProduct:
    sku: str
    offer_id: str | None
    title: str | None
    unit_economy: UnitEconomyProduct | None
    mapping_source: str
    status: str


class OzonAdAttributionCalculator:
    def calculate_import(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
        report: PromotionAnalyticsReport,
        products_by_sku: dict[str, ResolvedAttributionProduct],
        unit_economy_version: str | None,
        unit_economy_warning: str | None,
    ) -> OzonAdAttributionResponse:
        statistics = [
            row
            for row in report.statistics
            if campaign_id == "ALL" or row.campaign_id == campaign_id
        ]
        union = [
            row
            for row in report.union
            if campaign_id == "ALL" or row.campaign_id == campaign_id
        ]
        union_by_key: dict[_GroupKey, list[PromotionUnionRow]] = defaultdict(list)
        for row in union:
            union_by_key[_GroupKey(row.campaign_id, row.promoted_sku)].append(row)
        statistics_by_key: dict[
            _GroupKey,
            list[PromotionStatisticsRow],
        ] = defaultdict(list)
        for row in statistics:
            statistics_by_key[
                _GroupKey(row.campaign_id, row.promoted_sku)
            ].append(row)

        rows: list[OzonAdAttributionRow] = []
        errors: list[str] = []
        for key, statistic_rows in statistics_by_key.items():
            group_row, group_errors = self._build_import_row(
                statistic_rows,
                union_by_key.get(key, []),
                products_by_sku,
            )
            rows.append(group_row)
            errors.extend(group_errors)

        rows.sort(
            key=lambda row: (
                row.with_models.net_profit is None,
                row.with_models.net_profit or 0,
            )
        )
        return self._build_response(
            campaign_id=campaign_id,
            date_from=date_from,
            date_to=date_to,
            source="xlsx",
            report_state="IMPORTED",
            rows=rows,
            unit_economy_version=unit_economy_version,
            unit_economy_warning=unit_economy_warning,
            errors=errors,
        )

    def calculate_api(
        self,
        response: OzonSkuEfficiencyResponse,
    ) -> OzonAdAttributionResponse:
        rows: list[OzonAdAttributionRow] = []
        errors: list[str] = []
        for source in response.rows:
            if source.sku == "TOTAL":
                continue

            unit_cost = _optional_decimal(source.unit_expense_with_ozon_commission)
            direct_child = self._build_child(
                sale_type="direct",
                promoted_sku=source.sku,
                purchased_sku=source.sku,
                offer_id=source.offer_id,
                title=source.title,
                instrument=None,
                placement=None,
                quantity=source.direct_orders,
                revenue_with_vat=_decimal(source.direct_revenue_with_vat),
                unit_cost=unit_cost,
                mapping_source="seller_api+unit_economy",
                missing_status=(
                    "UNIT_COST_NOT_FOUND"
                    if source.offer_id
                    else "SKU_MAPPING_NOT_FOUND"
                ),
            )
            children = [direct_child]
            issues: list[str] = []
            if source.model_orders or source.model_revenue_with_vat:
                children.append(
                    OzonAdAttributionChild(
                        sale_type="model",
                        promoted_sku=source.sku,
                        purchased_sku="",
                        instrument=None,
                        placement=None,
                        title="SKU покупки недоступен в текстовом отчёте Ozon API",
                        quantity=source.model_orders,
                        revenue_with_vat=float(source.model_revenue_with_vat),
                        revenue_without_vat=float(
                            without_vat(_decimal(source.model_revenue_with_vat))
                        ),
                        average_price_without_vat=_safe_average(
                            without_vat(_decimal(source.model_revenue_with_vat)),
                            source.model_orders,
                        ),
                        mapping_source="api_aggregate",
                        status="MODEL_SKU_UNAVAILABLE",
                    )
                )
                issue = (
                    f"{source.sku}: Ozon API вернул модельные продажи без purchasedSku; "
                    "для точной себестоимости загрузи XLSX «Аналитика продвижения»."
                )
                issues.append(issue)
                errors.append(issue)

            spend = _decimal(source.ad_spend_without_vat)
            direct_metrics = self._metrics([direct_child], spend)
            with_models_metrics = self._metrics(children, spend)
            status = _row_status(children, with_models_metrics, issues)
            rows.append(
                OzonAdAttributionRow(
                    row_key=f"{source.campaign_id}:{source.sku}",
                    promoted_sku=source.sku,
                    offer_id=source.offer_id,
                    title=source.title,
                    campaign_ids=source.campaign_ids or [source.campaign_id],
                    campaign_titles=source.campaign_titles,
                    spend_without_vat=float(money(spend)),
                    direct=direct_metrics,
                    with_models=with_models_metrics,
                    children=children,
                    status=status,
                    issues=issues,
                )
            )

        rows.sort(
            key=lambda row: (
                row.with_models.net_profit is None,
                row.with_models.net_profit or 0,
            )
        )
        return self._build_response(
            campaign_id=response.campaign_id,
            date_from=response.date_from,
            date_to=response.date_to,
            source="ozon_api",
            report_state=response.report_state,
            rows=rows,
            unit_economy_version=response.unit_economy_version,
            unit_economy_warning=response.unit_economy_warning,
            errors=errors,
        )

    def _build_import_row(
        self,
        statistics: list[PromotionStatisticsRow],
        union_rows: list[PromotionUnionRow],
        products_by_sku: dict[str, ResolvedAttributionProduct],
    ) -> tuple[OzonAdAttributionRow, list[str]]:
        statistic = statistics[0]
        promoted_product = products_by_sku.get(statistic.promoted_sku)
        promoted_unit = (
            promoted_product.unit_economy if promoted_product is not None else None
        )
        children = [
            self._build_child(
                sale_type="direct",
                promoted_sku=current.promoted_sku,
                purchased_sku=current.promoted_sku,
                offer_id=promoted_product.offer_id if promoted_product else None,
                title=(
                    promoted_product.title if promoted_product is not None else None
                )
                or current.title,
                instrument=current.instrument,
                placement=current.placement,
                quantity=current.direct_orders,
                revenue_with_vat=current.direct_revenue_with_vat,
                unit_cost=_unit_cost(promoted_unit),
                mapping_source=(
                    promoted_product.mapping_source
                    if promoted_product is not None
                    else "not_found"
                ),
                missing_status=(
                    promoted_product.status
                    if promoted_product is not None
                    else "SKU_MAPPING_NOT_FOUND"
                ),
            )
            for current in statistics
        ]
        for union_row in union_rows:
            purchased_product = products_by_sku.get(union_row.purchased_sku)
            purchased_unit = (
                purchased_product.unit_economy
                if purchased_product is not None
                else None
            )
            children.append(
                self._build_child(
                    sale_type="model",
                    promoted_sku=statistic.promoted_sku,
                    purchased_sku=union_row.purchased_sku,
                    offer_id=(
                        purchased_product.offer_id if purchased_product else None
                    ),
                    title=(
                        purchased_product.title
                        if purchased_product is not None
                        else None
                    )
                    or union_row.purchased_title,
                    instrument=union_row.instrument,
                    placement=union_row.placement,
                    quantity=union_row.orders,
                    revenue_with_vat=union_row.revenue_with_vat,
                    unit_cost=_unit_cost(purchased_unit),
                    mapping_source=(
                        f"union+{purchased_product.mapping_source}"
                        if purchased_product is not None
                        else "union+not_found"
                    ),
                    missing_status=(
                        purchased_product.status
                        if purchased_product is not None
                        else "SKU_MAPPING_NOT_FOUND"
                    ),
                )
            )

        issues = self._validate_union(statistics, union_rows)
        for child in children:
            if child.quantity > 0 and child.unit_cost is None:
                issues.append(
                    f"{child.purchased_sku or statistic.promoted_sku}: "
                    f"{_status_message(child.status)}."
                )

        spend_without_vat = sum(
            (without_vat(current.spend_with_vat) for current in statistics),
            Decimal("0"),
        )
        direct_children = [
            child for child in children if child.sale_type == "direct"
        ]
        direct_metrics = self._metrics(direct_children, spend_without_vat)
        with_models_metrics = self._metrics(children, spend_without_vat)
        status = _row_status(children, with_models_metrics, issues)
        return (
            OzonAdAttributionRow(
                row_key=f"{statistic.campaign_id}:{statistic.promoted_sku}",
                promoted_sku=statistic.promoted_sku,
                offer_id=promoted_product.offer_id if promoted_product else None,
                title=(
                    promoted_product.title if promoted_product is not None else None
                )
                or statistic.title,
                campaign_ids=[statistic.campaign_id],
                spend_without_vat=float(spend_without_vat),
                direct=direct_metrics,
                with_models=with_models_metrics,
                children=children,
                status=status,
                issues=issues,
            ),
            issues,
        )

    def _build_child(
        self,
        sale_type: str,
        promoted_sku: str,
        purchased_sku: str,
        offer_id: str | None,
        title: str | None,
        instrument: str | None,
        placement: str | None,
        quantity: int,
        revenue_with_vat: Decimal,
        unit_cost: Decimal | None,
        mapping_source: str,
        missing_status: str = "UNIT_COST_NOT_FOUND",
    ) -> OzonAdAttributionChild:
        revenue_without_vat = without_vat(revenue_with_vat)
        average = _safe_average_decimal(revenue_without_vat, quantity)
        if quantity < 0 or (quantity == 0 and revenue_with_vat != 0):
            return OzonAdAttributionChild(
                sale_type=sale_type,
                promoted_sku=promoted_sku,
                purchased_sku=purchased_sku,
                instrument=instrument,
                placement=placement,
                offer_id=offer_id,
                title=title,
                quantity=quantity,
                revenue_with_vat=float(money(revenue_with_vat)),
                revenue_without_vat=float(money(revenue_without_vat)),
                average_price_without_vat=average,
                unit_cost=float(money(unit_cost)) if unit_cost is not None else None,
                mapping_source=mapping_source,
                status="INVALID_QUANTITY",
            )
        if revenue_with_vat < 0:
            return OzonAdAttributionChild(
                sale_type=sale_type,
                promoted_sku=promoted_sku,
                purchased_sku=purchased_sku,
                instrument=instrument,
                placement=placement,
                offer_id=offer_id,
                title=title,
                quantity=quantity,
                revenue_with_vat=float(money(revenue_with_vat)),
                revenue_without_vat=float(money(revenue_without_vat)),
                average_price_without_vat=average,
                unit_cost=float(money(unit_cost)) if unit_cost is not None else None,
                mapping_source=mapping_source,
                status="INVALID_REVENUE",
            )
        if quantity == 0:
            return OzonAdAttributionChild(
                sale_type=sale_type,
                promoted_sku=promoted_sku,
                purchased_sku=purchased_sku,
                instrument=instrument,
                placement=placement,
                offer_id=offer_id,
                title=title,
                quantity=quantity,
                revenue_with_vat=float(money(revenue_with_vat)),
                revenue_without_vat=float(revenue_without_vat),
                average_price_without_vat=average,
                unit_cost=float(unit_cost) if unit_cost is not None else None,
                total_cost=0.0,
                tax=0.0,
                profit_before_ads=0.0,
                mapping_source=mapping_source,
                status="NO_SALES",
            )

        if unit_cost is None:
            return OzonAdAttributionChild(
                sale_type=sale_type,
                promoted_sku=promoted_sku,
                purchased_sku=purchased_sku,
                instrument=instrument,
                placement=placement,
                offer_id=offer_id,
                title=title,
                quantity=quantity,
                revenue_with_vat=float(money(revenue_with_vat)),
                revenue_without_vat=float(revenue_without_vat),
                average_price_without_vat=average,
                mapping_source=mapping_source,
                status=missing_status,
            )

        total_cost = money(unit_cost * quantity)
        pre_tax = money(revenue_without_vat - total_cost)
        tax = profit_tax(pre_tax)
        return OzonAdAttributionChild(
            sale_type=sale_type,
            promoted_sku=promoted_sku,
            purchased_sku=purchased_sku,
            instrument=instrument,
            placement=placement,
            offer_id=offer_id,
            title=title,
            quantity=quantity,
            revenue_with_vat=float(money(revenue_with_vat)),
            revenue_without_vat=float(revenue_without_vat),
            average_price_without_vat=average,
            unit_cost=float(money(unit_cost)),
            total_cost=float(total_cost),
            tax=float(tax),
            profit_before_ads=float(money(pre_tax - tax)),
            mapping_source=mapping_source,
            status="OK",
        )

    def _metrics(
        self,
        children: list[OzonAdAttributionChild],
        spend_without_vat: Decimal,
    ) -> OzonAdAttributionMetrics:
        orders = sum(child.quantity for child in children)
        revenue_with_vat = sum(
            (_decimal(child.revenue_with_vat) for child in children),
            Decimal("0"),
        )
        revenue_without_vat = sum(
            (_decimal(child.revenue_without_vat) for child in children),
            Decimal("0"),
        )
        valid_children = [
            child
            for child in children
            if child.status in {"OK", "NO_SALES"}
        ]
        covered_orders = sum(
            child.quantity
            for child in valid_children
        )
        covered_revenue = sum(
            (_decimal(child.revenue_without_vat) for child in valid_children),
            Decimal("0"),
        )
        complete = all(
            child.status in {"OK", "NO_SALES"}
            for child in children
        )
        coverage_orders = Decimal("100") if orders == 0 else (
            Decimal(covered_orders) / Decimal(orders) * Decimal("100")
        )
        coverage = (
            Decimal("100")
            if revenue_without_vat == 0
            else covered_revenue / revenue_without_vat * Decimal("100")
        )

        total_cost = sum(
            (_decimal(child.total_cost) for child in valid_children),
            Decimal("0"),
        )
        tax = sum(
            (_decimal(child.tax) for child in valid_children),
            Decimal("0"),
        )
        profit_before_ads = sum(
            (_decimal(child.profit_before_ads) for child in valid_children),
            Decimal("0"),
        )
        net_profit = profit_before_ads - spend_without_vat

        drr = (
            money(spend_without_vat / revenue_without_vat * Decimal("100"))
            if revenue_without_vat > 0
            else None
        )
        romi = (
            money(net_profit / spend_without_vat * Decimal("100"))
            if net_profit is not None and spend_without_vat > 0
            else None
        )
        cost_per_order = (
            money(spend_without_vat / Decimal(orders)) if orders > 0 else None
        )
        return OzonAdAttributionMetrics(
            orders=orders,
            revenue_with_vat=float(money(revenue_with_vat)),
            revenue_without_vat=float(money(revenue_without_vat)),
            spend_without_vat=float(money(spend_without_vat)),
            total_cost=float(money(total_cost)) if total_cost is not None else None,
            tax=float(money(tax)) if tax is not None else None,
            profit_before_ads=(
                float(money(profit_before_ads))
                if profit_before_ads is not None
                else None
            ),
            net_profit=float(money(net_profit)) if net_profit is not None else None,
            drr_percent=float(drr) if drr is not None else None,
            romi_percent=float(romi) if romi is not None else None,
            cost_per_order=(
                float(cost_per_order) if cost_per_order is not None else None
            ),
            coverage_percent=float(money(coverage)),
            coverage_orders_percent=float(money(coverage_orders)),
            complete=complete,
        )

    def _validate_union(
        self,
        statistics: list[PromotionStatisticsRow],
        union_rows: list[PromotionUnionRow],
    ) -> list[str]:
        issues: list[str] = []
        for statistic in statistics:
            matching_union = [
                row
                for row in union_rows
                if row.instrument == statistic.instrument
                and row.placement == statistic.placement
            ]
            union_orders = sum(row.orders for row in matching_union)
            union_revenue = sum(
                (row.revenue_with_vat for row in matching_union),
                Decimal("0"),
            )
            if union_orders != statistic.model_orders:
                issues.append(
                    "UNION_QUANTITY_MISMATCH: "
                    f"{statistic.promoted_sku}, {statistic.instrument or '—'}, "
                    f"{statistic.placement or '—'}: Union содержит "
                    f"{union_orders} модельных заказов, Statistics — "
                    f"{statistic.model_orders}."
                )
            if (
                abs(union_revenue - statistic.model_revenue_with_vat)
                > Decimal("1")
            ):
                issues.append(
                    "UNION_REVENUE_MISMATCH: "
                    f"{statistic.promoted_sku}, {statistic.instrument or '—'}, "
                    f"{statistic.placement or '—'}: сумма моделей Union "
                    f"{money(union_revenue)} не совпадает со Statistics "
                    f"{money(statistic.model_revenue_with_vat)}."
                )
        return issues

    def _build_response(
        self,
        campaign_id: str,
        date_from: str,
        date_to: str,
        source: str,
        report_state: str,
        rows: list[OzonAdAttributionRow],
        unit_economy_version: str | None,
        unit_economy_warning: str | None,
        errors: list[str],
    ) -> OzonAdAttributionResponse:
        campaign_ids = {
            campaign
            for row in rows
            for campaign in row.campaign_ids
        }
        return OzonAdAttributionResponse(
            campaign_id=campaign_id,
            date_from=date_from,
            date_to=date_to,
            report_state=report_state,
            source=source,
            unit_economy_version=unit_economy_version,
            unit_economy_warning=unit_economy_warning,
            campaign_count=len(campaign_ids),
            rows=rows,
            direct_total=self._aggregate_metrics(
                [row.direct for row in rows]
            ),
            with_models_total=self._aggregate_metrics(
                [row.with_models for row in rows]
            ),
            errors=list(dict.fromkeys(errors)),
        )

    def _aggregate_metrics(
        self,
        metrics: list[OzonAdAttributionMetrics],
    ) -> OzonAdAttributionMetrics:
        orders = sum(item.orders for item in metrics)
        revenue_with_vat = sum(
            (_decimal(item.revenue_with_vat) for item in metrics),
            Decimal("0"),
        )
        revenue_without_vat = sum(
            (_decimal(item.revenue_without_vat) for item in metrics),
            Decimal("0"),
        )
        spend = sum(
            (_decimal(item.spend_without_vat) for item in metrics),
            Decimal("0"),
        )
        complete = all(item.complete for item in metrics)
        covered_revenue = sum(
            _decimal(item.revenue_without_vat)
            * _decimal(item.coverage_percent)
            / Decimal("100")
            for item in metrics
        )
        covered_orders = sum(
            Decimal(item.orders)
            * _decimal(item.coverage_orders_percent)
            / Decimal("100")
            for item in metrics
        )
        coverage = (
            Decimal("100")
            if revenue_without_vat == 0
            else covered_revenue
            / revenue_without_vat
            * Decimal("100")
        )
        coverage_orders = (
            Decimal("100")
            if orders == 0
            else covered_orders / Decimal(orders) * Decimal("100")
        )
        total_cost = _sum_optional(metrics, "total_cost")
        tax = _sum_optional(metrics, "tax")
        profit_before_ads = _sum_optional(metrics, "profit_before_ads")
        net_profit = _sum_optional(metrics, "net_profit")
        drr = (
            money(spend / revenue_without_vat * Decimal("100"))
            if revenue_without_vat > 0
            else None
        )
        romi = (
            money(net_profit / spend * Decimal("100"))
            if net_profit is not None and spend > 0
            else None
        )
        return OzonAdAttributionMetrics(
            orders=orders,
            revenue_with_vat=float(money(revenue_with_vat)),
            revenue_without_vat=float(money(revenue_without_vat)),
            spend_without_vat=float(money(spend)),
            total_cost=float(money(total_cost)) if total_cost is not None else None,
            tax=float(money(tax)) if tax is not None else None,
            profit_before_ads=(
                float(money(profit_before_ads))
                if profit_before_ads is not None
                else None
            ),
            net_profit=(
                float(money(net_profit)) if net_profit is not None else None
            ),
            drr_percent=float(drr) if drr is not None else None,
            romi_percent=float(romi) if romi is not None else None,
            cost_per_order=(
                float(money(spend / Decimal(orders))) if orders > 0 else None
            ),
            coverage_percent=float(money(coverage)),
            coverage_orders_percent=float(money(coverage_orders)),
            complete=complete,
        )


def _unit_cost(product: UnitEconomyProduct | None) -> Decimal | None:
    if product is None or product.expense_with_ozon_commission is None:
        return None
    return _decimal(product.expense_with_ozon_commission)


def _decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _safe_average_decimal(value: Decimal, quantity: int) -> float | None:
    if quantity <= 0:
        return None
    return float(money(value / Decimal(quantity)))


def _safe_average(value: Decimal, quantity: int) -> float | None:
    return _safe_average_decimal(value, quantity)


def _row_status(
    children: list[OzonAdAttributionChild],
    metrics: OzonAdAttributionMetrics,
    issues: list[str],
) -> str:
    for status in (
        "UNION_QUANTITY_MISMATCH",
        "UNION_REVENUE_MISMATCH",
    ):
        if any(issue.startswith(status) for issue in issues):
            return status
    if any(child.status == "MODEL_SKU_UNAVAILABLE" for child in children):
        return "MODEL_SKU_UNAVAILABLE"
    for status in (
        "SKU_MAPPING_CONFLICT",
        "SKU_MAPPING_NOT_FOUND",
        "UNIT_ECONOMICS_NOT_FOUND",
        "UNIT_COST_NOT_FOUND",
        "INVALID_QUANTITY",
        "INVALID_REVENUE",
        "TAX_CALCULATION_ERROR",
        "CALCULATION_ERROR",
    ):
        if any(child.status == status for child in children):
            return status
    if not metrics.complete:
        return "CALCULATION_ERROR"
    if metrics.orders == 0 and metrics.spend_without_vat > 0:
        return "SPEND_WITHOUT_SALES"
    return "OK"


def _status_message(status: str) -> str:
    return {
        "SKU_MAPPING_NOT_FOUND": "не найдено соответствие Ozon SKU и артикула",
        "SKU_MAPPING_CONFLICT": "найдено несколько соответствий Ozon SKU",
        "UNIT_ECONOMICS_NOT_FOUND": "артикул отсутствует в юнит-экономике",
        "UNIT_COST_NOT_FOUND": "в юнит-экономике не заполнен «Себес + комиссия»",
        "INVALID_QUANTITY": "некорректное количество",
        "INVALID_REVENUE": "некорректная рекламная выручка",
    }.get(status, f"расчёт не выполнен, статус {status}")


def _sum_optional(
    metrics: list[OzonAdAttributionMetrics],
    field_name: str,
) -> Decimal | None:
    values = [getattr(item, field_name) for item in metrics]
    if any(value is None for value in values):
        return None
    return sum((_decimal(value) for value in values), Decimal("0"))
