from dataclasses import dataclass
from collections.abc import Iterable
from decimal import Decimal

from app.schemas.ozon import (
    OzonCampaignModeledEconomics,
    OzonCampaignPerformanceMetrics,
    OzonCampaignProduct,
    OzonSkuEfficiencyRow,
    OzonSkuEfficiencyResponse,
    OzonSkuProfitBreakdown,
)
from app.services.ozon_total_sales_report_parser import OzonTotalSalesReportRow
from app.services.financial_calculator import (
    PROFIT_TAX_RATE as DECIMAL_PROFIT_TAX_RATE,
    VAT_MULTIPLIER as DECIMAL_VAT_MULTIPLIER,
    net_after_profit_tax,
    profit_tax,
)


VAT_MULTIPLIER = float(DECIMAL_VAT_MULTIPLIER)
VAT_RATE = VAT_MULTIPLIER - 1
PROFIT_TAX_RATE = float(DECIMAL_PROFIT_TAX_RATE)
PROFIT_TAX_LABEL = "налог на прибыль 22%"
MODEL_ATTRIBUTION_AVERAGE_CHECK_TOLERANCE = 0.25


@dataclass(frozen=True)
class OzonSkuEfficiencyCalculation:
    rows: list[OzonSkuEfficiencyRow]
    total: OzonSkuEfficiencyRow | None
    adjustment_ad_spend_with_vat: float
    adjustment_ad_spend_without_vat: float


class OzonAdEconomicsCalculator:
    def calculate_net_profit(self, profit_before_tax: float | None) -> float | None:
        return _calculate_net_profit(profit_before_tax)

    def normalize_profit_tax(
        self,
        response: OzonSkuEfficiencyResponse,
    ) -> OzonSkuEfficiencyResponse:
        return _normalize_profit_tax_response(response)

    def calculate_sku_efficiency(
        self,
        campaign_id: str,
        report_rows: list[dict[str, str]],
        products_by_sku: dict[str, OzonCampaignProduct],
    ) -> OzonSkuEfficiencyCalculation:
        sku_raw_rows = [
            raw_row
            for raw_row in report_rows
            if _is_sku_report_product_row(raw_row)
        ]
        adjustment_ad_spend_with_vat = sum(
            parse_decimal(raw_row.get("Расход, ₽, с НДС"))
            for raw_row in report_rows
            if _is_sku_report_adjustment_row(raw_row)
        )
        adjustment_ad_spend_without_vat = adjustment_ad_spend_with_vat / VAT_MULTIPLIER
        raw_rows = [
            self._build_sku_efficiency_row(campaign_id, raw_row, products_by_sku)
            for raw_row in sku_raw_rows
        ]
        grouped_rows: dict[str, list[OzonSkuEfficiencyRow]] = {}
        for row in raw_rows:
            grouped_rows.setdefault(row.sku, []).append(row)

        rows = [
            self._combine_sku_efficiency_rows(campaign_id, sku_rows)
            if len(sku_rows) > 1
            else sku_rows[0]
            for sku_rows in grouped_rows.values()
        ]
        total = self._build_total_sku_efficiency_row(
            campaign_id,
            rows,
            adjustment_ad_spend_with_vat,
            adjustment_ad_spend_without_vat,
        )

        return OzonSkuEfficiencyCalculation(
            rows=rows,
            total=total,
            adjustment_ad_spend_with_vat=adjustment_ad_spend_with_vat,
            adjustment_ad_spend_without_vat=adjustment_ad_spend_without_vat,
        )

    def combine_sku_efficiency_responses(
        self,
        campaign_id: str,
        responses: list[OzonSkuEfficiencyResponse],
    ) -> OzonSkuEfficiencyCalculation:
        grouped_rows: dict[str, list[OzonSkuEfficiencyRow]] = {}
        for response in responses:
            for row in response.rows:
                grouped_rows.setdefault(row.sku, []).append(row)

        rows = [
            self._combine_sku_efficiency_rows(campaign_id, sku_rows)
            for sku_rows in grouped_rows.values()
        ]
        total_adjustment_ad_spend_with_vat = sum(
            response.adjustment_ad_spend_with_vat for response in responses
        )
        total_adjustment_ad_spend_without_vat = sum(
            response.adjustment_ad_spend_without_vat for response in responses
        )
        total = self._build_total_sku_efficiency_row(
            campaign_id,
            rows,
            total_adjustment_ad_spend_with_vat,
            total_adjustment_ad_spend_without_vat,
        )

        return OzonSkuEfficiencyCalculation(
            rows=rows,
            total=total,
            adjustment_ad_spend_with_vat=total_adjustment_ad_spend_with_vat,
            adjustment_ad_spend_without_vat=total_adjustment_ad_spend_without_vat,
        )

    def enrich_with_total_sales(
        self,
        response: OzonSkuEfficiencyResponse,
        total_sales_rows: list[OzonTotalSalesReportRow],
    ) -> OzonSkuEfficiencyResponse:
        sales_by_offer_id = {
            _normalize_match_key(row.offer_id): row
            for row in total_sales_rows
            if row.offer_id is not None
        }
        sales_by_sku = {
            _normalize_match_key(row.sku): row
            for row in total_sales_rows
            if row.sku is not None
        }
        enriched_rows = [
            self._enrich_sku_row_with_total_sales(
                row,
                sales_by_offer_id.get(_normalize_match_key(row.offer_id))
                or sales_by_sku.get(_normalize_match_key(row.sku)),
            )
            for row in response.rows
        ]
        enriched_total = self._build_total_sku_efficiency_row(
            response.campaign_id,
            enriched_rows,
            response.adjustment_ad_spend_with_vat,
            response.adjustment_ad_spend_without_vat,
        )
        if enriched_total is not None:
            enriched_total = self._enrich_total_row_with_total_sales(
                enriched_total,
                enriched_rows,
            )

        return response.model_copy(
            update={
                "rows": enriched_rows,
                "total": enriched_total,
                "total_sales_report_state": "IMPORTED",
                "total_sales_warning": _build_total_sales_warning(
                    response,
                    enriched_rows,
                ),
            }
        )

    def build_modeled_economics(
        self,
        metrics: OzonCampaignPerformanceMetrics,
        products: list[OzonCampaignProduct],
    ) -> OzonCampaignModeledEconomics:
        revenue_without_vat = metrics.revenue / VAT_MULTIPLIER
        ad_spend_without_vat = metrics.ad_spend / VAT_MULTIPLIER
        average_order_revenue_without_vat = _safe_divide(
            revenue_without_vat,
            metrics.orders,
        )
        average_ad_spend_per_order_without_vat = _safe_divide(
            ad_spend_without_vat,
            metrics.orders,
        )
        break_even_expense = (
            average_order_revenue_without_vat - average_ad_spend_per_order_without_vat
            if average_order_revenue_without_vat is not None
            and average_ad_spend_per_order_without_vat is not None
            else None
        )

        unit_expenses = [
            product.unit_economy.expense_with_ozon_commission
            for product in products
            if product.unit_economy is not None
            and product.unit_economy.expense_with_ozon_commission is not None
        ]

        if not unit_expenses or metrics.orders <= 0:
            return OzonCampaignModeledEconomics(
                vat_multiplier=VAT_MULTIPLIER,
                revenue_without_vat=revenue_without_vat,
                ad_spend_without_vat=ad_spend_without_vat,
                average_order_revenue_without_vat=average_order_revenue_without_vat,
                average_ad_spend_per_order_without_vat=average_ad_spend_per_order_without_vat,
                break_even_expense_with_ozon_commission_per_order=break_even_expense,
                unit_expense_with_ozon_commission_min=None,
                unit_expense_with_ozon_commission_max=None,
                unit_expense_with_ozon_commission_avg=None,
                profit_before_tax_min=None,
                profit_before_tax_max=None,
                net_profit_min=None,
                net_profit_max=None,
                exact_profit_available=False,
                note=(
                    "No matched unit-economy cost or no orders. Profit cannot be modeled."
                ),
            )

        min_unit_expense = min(unit_expenses)
        max_unit_expense = max(unit_expenses)
        avg_unit_expense = sum(unit_expenses) / len(unit_expenses)
        exact_profit_available = len(unit_expenses) == 1 or len(products) == 1

        if exact_profit_available:
            profit_before_tax_min = (
                revenue_without_vat - ad_spend_without_vat - avg_unit_expense * metrics.orders
            )
            profit_before_tax_max = profit_before_tax_min
            note = (
                "Exact modeled campaign profit is available because the campaign has one "
                "matched advertised product."
            )
        else:
            profit_before_tax_min = (
                revenue_without_vat - ad_spend_without_vat - max_unit_expense * metrics.orders
            )
            profit_before_tax_max = (
                revenue_without_vat - ad_spend_without_vat - min_unit_expense * metrics.orders
            )
            note = (
                "Ozon returned campaign-level statistics only. SKU allocation is not "
                "invented; profit is shown as a range using min/max matched unit costs."
            )

        return OzonCampaignModeledEconomics(
            vat_multiplier=VAT_MULTIPLIER,
            revenue_without_vat=revenue_without_vat,
            ad_spend_without_vat=ad_spend_without_vat,
            average_order_revenue_without_vat=average_order_revenue_without_vat,
            average_ad_spend_per_order_without_vat=average_ad_spend_per_order_without_vat,
            break_even_expense_with_ozon_commission_per_order=break_even_expense,
            unit_expense_with_ozon_commission_min=min_unit_expense,
            unit_expense_with_ozon_commission_max=max_unit_expense,
            unit_expense_with_ozon_commission_avg=avg_unit_expense,
            profit_before_tax_min=profit_before_tax_min,
            profit_before_tax_max=profit_before_tax_max,
            net_profit_min=_calculate_net_profit(profit_before_tax_min),
            net_profit_max=_calculate_net_profit(profit_before_tax_max),
            exact_profit_available=exact_profit_available,
            note=note,
        )

    def _build_sku_efficiency_row(
        self,
        campaign_id: str,
        raw_row: dict[str, str],
        products_by_sku: dict[str, OzonCampaignProduct],
    ) -> OzonSkuEfficiencyRow:
        sku = raw_row.get("sku", "")
        product = products_by_sku.get(sku)
        unit_product = product.unit_economy if product is not None else None
        direct_revenue_with_vat = parse_decimal(raw_row.get("Продажи, ₽"))
        model_revenue_with_vat = parse_decimal(raw_row.get("Продажи с заказов модели, ₽"))
        revenue_with_vat = direct_revenue_with_vat + model_revenue_with_vat
        ad_spend_with_vat = parse_decimal(raw_row.get("Расход, ₽, с НДС"))
        total_ordered_amount_with_vat = parse_decimal(raw_row.get("Заказано на сумму, ₽"))
        revenue_without_vat = revenue_with_vat / VAT_MULTIPLIER
        direct_revenue_without_vat = direct_revenue_with_vat / VAT_MULTIPLIER
        model_revenue_without_vat = model_revenue_with_vat / VAT_MULTIPLIER
        ad_spend_without_vat = ad_spend_with_vat / VAT_MULTIPLIER
        direct_orders = parse_int(raw_row.get("Заказы"))
        model_orders = parse_int(raw_row.get("Заказы модели"))
        orders = direct_orders + model_orders
        model_attribution_included_in_sku = can_include_model_attribution_in_sku(
            total_ordered_amount_with_vat=total_ordered_amount_with_vat,
            attribution_revenue_with_vat=revenue_with_vat,
            model_revenue_with_vat=model_revenue_with_vat,
            direct_revenue_with_vat=direct_revenue_with_vat,
            direct_orders=direct_orders,
            model_orders=model_orders,
        )
        sku_orders = direct_orders
        sku_revenue_with_vat = direct_revenue_with_vat
        sku_revenue_without_vat = sku_revenue_with_vat / VAT_MULTIPLIER
        attribution_profit_orders = (
            orders if model_attribution_included_in_sku else direct_orders
        )
        attribution_profit_revenue_with_vat = (
            revenue_with_vat
            if model_attribution_included_in_sku
            else direct_revenue_with_vat
        )
        attribution_profit_revenue_without_vat = (
            attribution_profit_revenue_with_vat / VAT_MULTIPLIER
        )
        average_ad_order_revenue_with_vat = _safe_divide(
            attribution_profit_revenue_with_vat,
            attribution_profit_orders,
        )
        average_ad_order_revenue_without_vat = _safe_divide(
            attribution_profit_revenue_without_vat,
            attribution_profit_orders,
        )
        unit_economy_price_with_vat = (
            unit_product.price_with_vat
            if unit_product is not None
            else None
        )
        unit_economy_price_without_vat = (
            unit_product.price_without_vat
            if unit_product is not None
            else None
        )
        promotion_summary = _summarize_promotions(
            product.promotions if product is not None else []
        )
        sku_ad_spend_without_vat = _allocate_direct_sku_ad_spend(
            attribution_profit_revenue_without_vat,
            revenue_without_vat,
            ad_spend_without_vat,
        )
        unit_expense = (
            unit_product.expense_with_ozon_commission
            if unit_product is not None
            else None
        )
        profit_before_tax = (
            attribution_profit_revenue_without_vat
            - sku_ad_spend_without_vat
            - unit_expense * attribution_profit_orders
            if unit_expense is not None
            else None
        )
        tax_amount = _calculate_profit_tax(profit_before_tax)
        net_profit = _calculate_net_profit(profit_before_tax)

        return OzonSkuEfficiencyRow(
            campaign_id=campaign_id,
            campaign_ids=_source_campaign_ids(raw_row, campaign_id),
            campaign_titles=_source_campaign_titles(raw_row),
            sku=sku,
            offer_id=product.offer_id if product is not None else None,
            title=raw_row.get("Название товара") or (product.title if product is not None else None),
            views=parse_int(raw_row.get("Показы")),
            clicks=parse_int(raw_row.get("Клики")),
            to_cart=parse_int(raw_row.get("В корзину")),
            orders=orders,
            direct_orders=direct_orders,
            sku_orders=sku_orders,
            revenue_with_vat=revenue_with_vat,
            revenue_without_vat=revenue_without_vat,
            direct_revenue_with_vat=direct_revenue_with_vat,
            direct_revenue_without_vat=direct_revenue_without_vat,
            sku_revenue_with_vat=sku_revenue_with_vat,
            sku_revenue_without_vat=sku_revenue_without_vat,
            model_revenue_without_vat=model_revenue_without_vat,
            ad_spend_with_vat=ad_spend_with_vat,
            ad_spend_without_vat=ad_spend_without_vat,
            sku_ad_spend_without_vat=sku_ad_spend_without_vat,
            model_attribution_included_in_sku=model_attribution_included_in_sku,
            drr_percent=parse_optional_decimal(raw_row.get("ДРР, %")),
            ctr_percent=parse_optional_decimal(raw_row.get("CTR (%)")),
            average_cpc=parse_optional_decimal(raw_row.get("Средняя стоимость клика, ₽")),
            model_orders=model_orders,
            model_revenue_with_vat=model_revenue_with_vat,
            total_ordered_amount_with_vat=total_ordered_amount_with_vat,
            unit_expense_with_ozon_commission=unit_expense,
            unit_economy_price_with_vat=unit_economy_price_with_vat,
            unit_economy_price_without_vat=unit_economy_price_without_vat,
            average_ad_order_revenue_with_vat=average_ad_order_revenue_with_vat,
            average_ad_order_revenue_without_vat=average_ad_order_revenue_without_vat,
            ad_price_discount_percent=_calculate_price_discount_percent(
                average_ad_order_revenue_without_vat,
                unit_economy_price_without_vat,
            ),
            promotion_matched=promotion_summary["matched"],
            promotion_count=promotion_summary["count"],
            promotion_action_ids=promotion_summary["action_ids"],
            promotion_titles=promotion_summary["titles"],
            promotion_price_with_vat=promotion_summary["price_with_vat"],
            promotion_discount_percent=promotion_summary["discount_percent"],
            profit_before_tax=profit_before_tax,
            net_profit=net_profit,
            profit_breakdown=_build_profit_breakdown(
                revenue_without_vat=attribution_profit_revenue_without_vat,
                ad_spend_without_vat=sku_ad_spend_without_vat,
                unit_expense_per_order=unit_expense,
                orders=attribution_profit_orders,
                profit_before_tax=profit_before_tax,
                tax_amount=tax_amount,
                net_profit=net_profit,
                unit_economy_price_without_vat=(
                    unit_product.price_without_vat
                    if unit_product is not None
                    else None
                ),
                unit_economy_profit_before_tax=(
                    unit_product.profit_before_tax
                    if unit_product is not None
                    else None
                ),
                unit_economy_net_profit=(
                    unit_product.net_profit
                    if unit_product is not None
                    else None
                ),
            ),
            matched_unit_economy=unit_expense is not None,
        )

    def _combine_sku_efficiency_rows(
        self,
        campaign_id: str,
        rows: list[OzonSkuEfficiencyRow],
    ) -> OzonSkuEfficiencyRow:
        first = rows[0]
        revenue_with_vat = sum(row.revenue_with_vat for row in rows)
        revenue_without_vat = sum(row.revenue_without_vat for row in rows)
        direct_revenue_with_vat = sum(row.direct_revenue_with_vat for row in rows)
        direct_revenue_without_vat = sum(row.direct_revenue_without_vat for row in rows)
        sku_revenue_with_vat = sum(row.sku_revenue_with_vat for row in rows)
        sku_revenue_without_vat = sum(row.sku_revenue_without_vat for row in rows)
        model_revenue_with_vat = sum(row.model_revenue_with_vat for row in rows)
        model_revenue_without_vat = sum(row.model_revenue_without_vat for row in rows)
        ad_spend_with_vat = sum(row.ad_spend_with_vat for row in rows)
        ad_spend_without_vat = sum(row.ad_spend_without_vat for row in rows)
        sku_ad_spend_without_vat = sum(row.sku_ad_spend_without_vat for row in rows)
        profit_revenue_without_vat = _sum_known_values(
            [
                row.profit_breakdown.revenue_without_vat
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        profit_orders = _sum_known_int_values(
            [
                row.profit_breakdown.orders
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        clicks = sum(row.clicks for row in rows)
        views = sum(row.views for row in rows)
        orders = sum(row.orders for row in rows)
        direct_orders = sum(row.direct_orders for row in rows)
        sku_orders = sum(row.sku_orders for row in rows)
        profit_before_tax = _sum_optional_values(
            [row.profit_before_tax for row in rows]
        )
        tax_amount = _calculate_profit_tax(profit_before_tax)
        net_profit = _calculate_net_profit(profit_before_tax)
        unit_expense = _display_unit_expense(rows)
        unit_economy_price_with_vat = _weighted_average(
            [
                (row.unit_economy_price_with_vat, row.profit_breakdown.orders)
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        unit_economy_price_without_vat = _weighted_average(
            [
                (row.unit_economy_price_without_vat, row.profit_breakdown.orders)
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        average_ad_order_revenue_without_vat = (
            _safe_divide(profit_revenue_without_vat, profit_orders)
            if profit_revenue_without_vat is not None and profit_orders is not None
            else None
        )
        average_ad_order_revenue_with_vat = (
            average_ad_order_revenue_without_vat * VAT_MULTIPLIER
            if average_ad_order_revenue_without_vat is not None
            else None
        )
        unit_expense_total = _sum_known_values(
            [
                row.profit_breakdown.unit_expense_total
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        promotion_summary = _merge_row_promotion_summary(rows)

        return OzonSkuEfficiencyRow(
            campaign_id=campaign_id,
            campaign_ids=_merge_string_lists(row.campaign_ids for row in rows),
            campaign_titles=_merge_string_lists(row.campaign_titles for row in rows),
            sku=first.sku,
            offer_id=first.offer_id,
            title=next((row.title for row in rows if row.title), first.title),
            views=views,
            clicks=clicks,
            to_cart=sum(row.to_cart for row in rows),
            orders=orders,
            direct_orders=direct_orders,
            sku_orders=sku_orders,
            revenue_with_vat=revenue_with_vat,
            revenue_without_vat=revenue_without_vat,
            direct_revenue_with_vat=direct_revenue_with_vat,
            direct_revenue_without_vat=direct_revenue_without_vat,
            sku_revenue_with_vat=sku_revenue_with_vat,
            sku_revenue_without_vat=sku_revenue_without_vat,
            model_revenue_without_vat=model_revenue_without_vat,
            ad_spend_with_vat=ad_spend_with_vat,
            ad_spend_without_vat=ad_spend_without_vat,
            sku_ad_spend_without_vat=sku_ad_spend_without_vat,
            model_attribution_included_in_sku=any(
                row.model_attribution_included_in_sku for row in rows
            ),
            drr_percent=(ad_spend_with_vat / revenue_with_vat * 100)
            if revenue_with_vat
            else None,
            ctr_percent=(clicks / views * 100) if views else None,
            average_cpc=(ad_spend_with_vat / clicks) if clicks else None,
            model_orders=sum(row.model_orders for row in rows),
            model_revenue_with_vat=model_revenue_with_vat,
            total_ordered_amount_with_vat=sum(
                row.total_ordered_amount_with_vat for row in rows
            ),
            unit_expense_with_ozon_commission=unit_expense,
            unit_economy_price_with_vat=unit_economy_price_with_vat,
            unit_economy_price_without_vat=unit_economy_price_without_vat,
            average_ad_order_revenue_with_vat=average_ad_order_revenue_with_vat,
            average_ad_order_revenue_without_vat=average_ad_order_revenue_without_vat,
            ad_price_discount_percent=_calculate_price_discount_percent(
                average_ad_order_revenue_without_vat,
                unit_economy_price_without_vat,
            ),
            promotion_matched=promotion_summary["matched"],
            promotion_count=promotion_summary["count"],
            promotion_action_ids=promotion_summary["action_ids"],
            promotion_titles=promotion_summary["titles"],
            promotion_price_with_vat=promotion_summary["price_with_vat"],
            promotion_discount_percent=promotion_summary["discount_percent"],
            profit_before_tax=profit_before_tax,
            net_profit=net_profit,
            profit_breakdown=_build_profit_breakdown(
                revenue_without_vat=profit_revenue_without_vat,
                ad_spend_without_vat=sku_ad_spend_without_vat,
                unit_expense_per_order=unit_expense,
                orders=profit_orders,
                profit_before_tax=profit_before_tax,
                tax_amount=tax_amount,
                net_profit=net_profit,
                unit_expense_total=unit_expense_total,
            ),
            matched_unit_economy=unit_expense is not None,
        )

    def _enrich_sku_row_with_total_sales(
        self,
        row: OzonSkuEfficiencyRow,
        total_sales_row: OzonTotalSalesReportRow | None,
    ) -> OzonSkuEfficiencyRow:
        if total_sales_row is None:
            return row.model_copy(
                update={
                    "total_sales_matched": False,
                }
            )

        total_sales_revenue_without_vat = (
            total_sales_row.ordered_amount_with_vat / VAT_MULTIPLIER
        )
        organic_orders = max(total_sales_row.orders - row.sku_orders, 0)
        average_total_order_revenue_without_vat = _safe_divide(
            total_sales_revenue_without_vat,
            total_sales_row.orders,
        )
        organic_revenue_without_vat = max(
            total_sales_revenue_without_vat - row.sku_revenue_without_vat,
            0,
        )
        average_organic_order_revenue_without_vat = _safe_divide(
            organic_revenue_without_vat,
            organic_orders,
        )
        unit_expense = _row_unit_expense_for_total_sales(row)
        organic_unit_expense_total = (
            unit_expense * organic_orders
            if unit_expense is not None
            else None
        )
        organic_profit_before_tax = (
            organic_revenue_without_vat - organic_unit_expense_total
            if organic_revenue_without_vat is not None
            and organic_unit_expense_total is not None
            else None
        )
        organic_net_profit = (
            _calculate_net_profit(organic_profit_before_tax)
            if organic_profit_before_tax is not None
            else None
        )
        all_sales_profit_before_tax = (
            total_sales_revenue_without_vat
            - row.sku_ad_spend_without_vat
            - unit_expense * total_sales_row.orders
            if unit_expense is not None
            else None
        )
        all_sales_net_profit = (
            _calculate_net_profit(all_sales_profit_before_tax)
            if all_sales_profit_before_tax is not None
            else None
        )

        return row.model_copy(
            update={
                "total_sales_orders": total_sales_row.orders,
                "total_sales_revenue_with_vat": total_sales_row.ordered_amount_with_vat,
                "total_sales_revenue_without_vat": total_sales_revenue_without_vat,
                "total_sales_drr_percent": (
                    row.ad_spend_without_vat / total_sales_revenue_without_vat * 100
                    if total_sales_revenue_without_vat
                    else None
                ),
                "average_total_order_revenue_without_vat": (
                    average_total_order_revenue_without_vat
                ),
                "total_price_discount_percent": _calculate_price_discount_percent(
                    average_total_order_revenue_without_vat,
                    row.unit_economy_price_without_vat,
                ),
                "organic_orders": organic_orders,
                "organic_revenue_without_vat": organic_revenue_without_vat,
                "average_organic_order_revenue_without_vat": (
                    average_organic_order_revenue_without_vat
                ),
                "organic_price_discount_percent": _calculate_price_discount_percent(
                    average_organic_order_revenue_without_vat,
                    row.unit_economy_price_without_vat,
                ),
                "organic_unit_expense_total": organic_unit_expense_total,
                "organic_profit_before_tax": organic_profit_before_tax,
                "organic_net_profit": organic_net_profit,
                "all_sales_profit_before_tax": all_sales_profit_before_tax,
                "all_sales_net_profit": all_sales_net_profit,
                "total_sales_matched": True,
            }
        )

    def _enrich_total_row_with_total_sales(
        self,
        total: OzonSkuEfficiencyRow,
        rows: list[OzonSkuEfficiencyRow],
    ) -> OzonSkuEfficiencyRow:
        total_sales_revenue_without_vat = _sum_known_values(
            [row.total_sales_revenue_without_vat for row in rows]
        )
        total_sales_revenue_with_vat = _sum_known_values(
            [row.total_sales_revenue_with_vat for row in rows]
        )
        total_sales_orders = _sum_known_int_values(
            [row.total_sales_orders for row in rows]
        )
        organic_orders = _sum_known_int_values([row.organic_orders for row in rows])
        organic_revenue_without_vat = _sum_known_values(
            [row.organic_revenue_without_vat for row in rows]
        )
        organic_unit_expense_total = _sum_known_values(
            [row.organic_unit_expense_total for row in rows]
        )
        organic_profit_before_tax = _sum_known_values(
            [row.organic_profit_before_tax for row in rows]
        )
        organic_net_profit = _calculate_net_profit(organic_profit_before_tax)
        all_sales_profit_before_tax = _sum_known_values(
            [row.all_sales_profit_before_tax for row in rows]
        )
        all_sales_net_profit = _calculate_net_profit(all_sales_profit_before_tax)
        total_price_weight = [
            (row.average_total_order_revenue_without_vat, row.total_sales_orders)
            for row in rows
        ]
        organic_price_weight = [
            (row.average_organic_order_revenue_without_vat, row.organic_orders)
            for row in rows
        ]

        return total.model_copy(
            update={
                "total_sales_orders": total_sales_orders,
                "total_sales_revenue_with_vat": total_sales_revenue_with_vat,
                "total_sales_revenue_without_vat": total_sales_revenue_without_vat,
                "total_sales_drr_percent": (
                    total.ad_spend_without_vat / total_sales_revenue_without_vat * 100
                    if total_sales_revenue_without_vat
                    else None
                ),
                "average_total_order_revenue_without_vat": (
                    _safe_divide(total_sales_revenue_without_vat, total_sales_orders)
                    if total_sales_revenue_without_vat is not None
                    and total_sales_orders is not None
                    else None
                ),
                "total_price_discount_percent": None,
                "organic_orders": organic_orders,
                "organic_revenue_without_vat": organic_revenue_without_vat,
                "average_organic_order_revenue_without_vat": _weighted_average(
                    organic_price_weight
                ),
                "organic_price_discount_percent": None,
                "organic_unit_expense_total": organic_unit_expense_total,
                "organic_profit_before_tax": organic_profit_before_tax,
                "organic_net_profit": organic_net_profit,
                "all_sales_profit_before_tax": all_sales_profit_before_tax,
                "all_sales_net_profit": all_sales_net_profit,
                "total_sales_matched": all(row.total_sales_matched for row in rows),
            }
        )

    def _build_total_sku_efficiency_row(
        self,
        campaign_id: str,
        rows: list[OzonSkuEfficiencyRow],
        adjustment_ad_spend_with_vat: float,
        adjustment_ad_spend_without_vat: float,
    ) -> OzonSkuEfficiencyRow | None:
        if not rows:
            return None

        revenue_with_vat = sum(row.revenue_with_vat for row in rows)
        direct_revenue_with_vat = sum(row.direct_revenue_with_vat for row in rows)
        direct_revenue_without_vat = sum(row.direct_revenue_without_vat for row in rows)
        sku_revenue_with_vat = sum(row.sku_revenue_with_vat for row in rows)
        sku_revenue_without_vat = sum(row.sku_revenue_without_vat for row in rows)
        model_revenue_with_vat = sum(row.model_revenue_with_vat for row in rows)
        model_revenue_without_vat = sum(row.model_revenue_without_vat for row in rows)
        sku_ad_spend_without_vat = (
            sum(row.sku_ad_spend_without_vat for row in rows)
            + adjustment_ad_spend_without_vat
        )
        ad_spend_with_vat = (
            sum(row.ad_spend_with_vat for row in rows) + adjustment_ad_spend_with_vat
        )
        revenue_without_vat = sum(row.revenue_without_vat for row in rows)
        ad_spend_without_vat = (
            sum(row.ad_spend_without_vat for row in rows) + adjustment_ad_spend_without_vat
        )
        clicks = sum(row.clicks for row in rows)
        profit_before_tax_values = [
            row.profit_before_tax for row in rows if row.profit_before_tax is not None
        ]
        profit_before_tax = (
            sum(profit_before_tax_values) - adjustment_ad_spend_without_vat
            if profit_before_tax_values
            else None
        )
        unit_expense_total = _sum_known_values(
            [
                row.profit_breakdown.unit_expense_total
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        profit_revenue_without_vat = _sum_known_values(
            [
                row.profit_breakdown.revenue_without_vat
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        profit_orders = _sum_known_int_values(
            [
                row.profit_breakdown.orders
                for row in rows
                if row.profit_breakdown is not None
            ]
        )
        tax_amount = _calculate_profit_tax(profit_before_tax)
        net_profit = _calculate_net_profit(profit_before_tax)
        promotion_summary = _merge_row_promotion_summary(rows)

        return OzonSkuEfficiencyRow(
            campaign_id=campaign_id,
            campaign_ids=_merge_string_lists(row.campaign_ids for row in rows),
            campaign_titles=_merge_string_lists(row.campaign_titles for row in rows),
            sku="TOTAL",
            offer_id=None,
            title="Итого",
            views=sum(row.views for row in rows),
            clicks=clicks,
            to_cart=sum(row.to_cart for row in rows),
            orders=sum(row.orders for row in rows),
            direct_orders=sum(row.direct_orders for row in rows),
            sku_orders=sum(row.sku_orders for row in rows),
            revenue_with_vat=revenue_with_vat,
            revenue_without_vat=revenue_without_vat,
            direct_revenue_with_vat=direct_revenue_with_vat,
            direct_revenue_without_vat=direct_revenue_without_vat,
            sku_revenue_with_vat=sku_revenue_with_vat,
            sku_revenue_without_vat=sku_revenue_without_vat,
            model_revenue_without_vat=model_revenue_without_vat,
            ad_spend_with_vat=ad_spend_with_vat,
            ad_spend_without_vat=ad_spend_without_vat,
            sku_ad_spend_without_vat=sku_ad_spend_without_vat,
            model_attribution_included_in_sku=any(
                row.model_attribution_included_in_sku for row in rows
            ),
            drr_percent=(ad_spend_with_vat / revenue_with_vat * 100)
            if revenue_with_vat
            else None,
            ctr_percent=None,
            average_cpc=(ad_spend_with_vat / clicks) if clicks else None,
            model_orders=sum(row.model_orders for row in rows),
            model_revenue_with_vat=model_revenue_with_vat,
            total_ordered_amount_with_vat=sum(row.total_ordered_amount_with_vat for row in rows),
            unit_expense_with_ozon_commission=None,
            unit_economy_price_with_vat=None,
            unit_economy_price_without_vat=None,
            average_ad_order_revenue_with_vat=(
                (profit_revenue_without_vat * VAT_MULTIPLIER / profit_orders)
                if profit_revenue_without_vat is not None and profit_orders
                else None
            ),
            average_ad_order_revenue_without_vat=(
                profit_revenue_without_vat / profit_orders
                if profit_revenue_without_vat is not None and profit_orders
                else None
            ),
            ad_price_discount_percent=None,
            promotion_matched=promotion_summary["matched"],
            promotion_count=promotion_summary["count"],
            promotion_action_ids=promotion_summary["action_ids"],
            promotion_titles=promotion_summary["titles"],
            promotion_price_with_vat=promotion_summary["price_with_vat"],
            promotion_discount_percent=promotion_summary["discount_percent"],
            profit_before_tax=profit_before_tax,
            net_profit=net_profit,
            profit_breakdown=_build_profit_breakdown(
                revenue_without_vat=profit_revenue_without_vat,
                ad_spend_without_vat=sku_ad_spend_without_vat,
                unit_expense_per_order=None,
                orders=profit_orders,
                profit_before_tax=profit_before_tax,
                tax_amount=tax_amount,
                net_profit=net_profit,
                unit_expense_total=unit_expense_total,
            ),
            matched_unit_economy=(
                profit_before_tax is not None
                and len(profit_before_tax_values) == len(rows)
            ),
        )


def parse_decimal(value: object) -> float:
    if value is None:
        return 0

    normalized = str(value).replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return 0


def parse_optional_decimal(value: object) -> float | None:
    if value is None:
        return None

    return parse_decimal(value)


def parse_int(value: object) -> int:
    if value is None:
        return 0

    normalized = str(value).replace(" ", "")
    try:
        return int(float(normalized.replace(",", ".")))
    except ValueError:
        return 0


def _is_sku_report_product_row(raw_row: dict[str, str]) -> bool:
    sku = raw_row.get("sku", "")
    return sku.isdigit()


def _is_sku_report_adjustment_row(raw_row: dict[str, str]) -> bool:
    return raw_row.get("sku") == "Корректировка"


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None

    return numerator / denominator


def _calculate_profit_tax(profit_before_tax: float | None) -> float | None:
    if profit_before_tax is None:
        return None

    return float(profit_tax(Decimal(str(profit_before_tax))))


def _calculate_net_profit(profit_before_tax: float | None) -> float | None:
    if profit_before_tax is None:
        return None

    return float(net_after_profit_tax(Decimal(str(profit_before_tax))))


def _normalize_profit_tax_response(
    response: OzonSkuEfficiencyResponse,
) -> OzonSkuEfficiencyResponse:
    return response.model_copy(
        update={
            "rows": [_normalize_profit_tax_row(row) for row in response.rows],
            "total": (
                _normalize_profit_tax_row(response.total)
                if response.total is not None
                else None
            ),
            "segments": [
                segment.model_copy(
                    update={
                        "rows": [
                            _normalize_profit_tax_row(row)
                            for row in segment.rows
                        ],
                        "total": (
                            _normalize_profit_tax_row(segment.total)
                            if segment.total is not None
                            else None
                        ),
                    }
                )
                for segment in response.segments
            ],
        }
    )


def _normalize_profit_tax_row(
    row: OzonSkuEfficiencyRow,
) -> OzonSkuEfficiencyRow:
    tax_amount = _calculate_profit_tax(row.profit_before_tax)
    net_profit = _calculate_net_profit(row.profit_before_tax)
    organic_net_profit = _calculate_net_profit(row.organic_profit_before_tax)
    all_sales_net_profit = _calculate_net_profit(row.all_sales_profit_before_tax)
    profit_breakdown = (
        row.profit_breakdown.model_copy(
            update={
                "tax_amount": tax_amount,
                "tax_amount_per_order": _safe_divide(
                    tax_amount,
                    row.profit_breakdown.orders,
                )
                if tax_amount is not None
                else None,
                "net_profit": net_profit,
                "net_profit_per_order": _safe_divide(
                    net_profit,
                    row.profit_breakdown.orders,
                )
                if net_profit is not None
                else None,
                "net_profit_formula": (
                    f"Прибыль до налога {_money(row.profit_before_tax)} - "
                    f"{PROFIT_TAX_LABEL} {_money(tax_amount)} = {_money(net_profit)}"
                    if row.profit_before_tax is not None
                    else "Нет прибыли до налога: чистая прибыль не рассчитана"
                ),
            }
        )
        if row.profit_breakdown is not None
        else None
    )

    return row.model_copy(
        update={
            "net_profit": net_profit,
            "organic_net_profit": organic_net_profit,
            "all_sales_net_profit": all_sales_net_profit,
            "profit_breakdown": profit_breakdown,
        }
    )


def _allocate_direct_sku_ad_spend(
    direct_revenue_without_vat: float,
    attribution_revenue_without_vat: float,
    ad_spend_without_vat: float,
) -> float:
    if attribution_revenue_without_vat > 0:
        return ad_spend_without_vat * (
            direct_revenue_without_vat / attribution_revenue_without_vat
        )

    return ad_spend_without_vat


def can_include_model_attribution_in_sku(
    total_ordered_amount_with_vat: float,
    attribution_revenue_with_vat: float,
    model_revenue_with_vat: float,
    direct_revenue_with_vat: float,
    direct_orders: int,
    model_orders: int,
) -> bool:
    if (
        model_revenue_with_vat <= 0
        or attribution_revenue_with_vat <= 0
        or direct_revenue_with_vat <= 0
        or direct_orders <= 0
        or model_orders <= 0
    ):
        return False

    tolerance = max(1, attribution_revenue_with_vat * 0.01)
    if total_ordered_amount_with_vat + tolerance < attribution_revenue_with_vat:
        return False

    direct_average = direct_revenue_with_vat / direct_orders
    model_average = model_revenue_with_vat / model_orders
    average_base = max(abs(direct_average), abs(model_average), 1)
    average_delta = abs(direct_average - model_average) / average_base
    return average_delta <= MODEL_ATTRIBUTION_AVERAGE_CHECK_TOLERANCE


def _sum_optional_values(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None

    return sum(value for value in values if value is not None)


def _sum_optional_int_values(values: list[int | None]) -> int | None:
    if any(value is None for value in values):
        return None

    return sum(value for value in values if value is not None)


def _sum_known_values(values: list[float | None]) -> float | None:
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None

    return sum(known_values)


def _sum_known_int_values(values: list[int | None]) -> int | None:
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None

    return sum(known_values)


def _weighted_average(values: list[tuple[float | None, int | None]]) -> float | None:
    known_values = [
        (value, weight)
        for value, weight in values
        if value is not None and weight is not None and weight > 0
    ]
    total_weight = sum(weight for _, weight in known_values)
    if total_weight <= 0:
        return None

    return sum(value * weight for value, weight in known_values) / total_weight


def _calculate_price_discount_percent(
    actual_price_with_vat: float | None,
    unit_price_with_vat: float | None,
) -> float | None:
    if (
        actual_price_with_vat is None
        or unit_price_with_vat is None
        or unit_price_with_vat <= 0
    ):
        return None

    return (1 - actual_price_with_vat / unit_price_with_vat) * 100


def _summarize_promotions(promotions: Iterable[object]) -> dict[str, object]:
    action_ids: list[str] = []
    titles: list[str] = []
    prices: list[float] = []
    discounts: list[float] = []
    seen_ids: set[str] = set()

    for promotion in promotions:
        action_id = str(getattr(promotion, "action_id", "") or "").strip()
        if action_id and action_id not in seen_ids:
            seen_ids.add(action_id)
            action_ids.append(action_id)

        title = str(getattr(promotion, "title", "") or "").strip()
        if title and title not in titles:
            titles.append(title)

        action_price = getattr(promotion, "action_price_with_vat", None)
        max_action_price = getattr(promotion, "max_action_price_with_vat", None)
        price = action_price if action_price is not None else max_action_price
        if price is not None:
            prices.append(float(price))

        discount = getattr(promotion, "discount_percent", None)
        if discount is not None:
            discounts.append(float(discount))

    return {
        "matched": bool(action_ids or titles),
        "count": len(action_ids or titles),
        "action_ids": action_ids,
        "titles": titles,
        "price_with_vat": min(prices) if prices else None,
        "discount_percent": max(discounts) if discounts else None,
    }


def _merge_row_promotion_summary(rows: list[OzonSkuEfficiencyRow]) -> dict[str, object]:
    action_ids = _merge_string_lists(row.promotion_action_ids for row in rows)
    titles = _merge_string_lists(row.promotion_titles for row in rows)
    prices = [
        row.promotion_price_with_vat
        for row in rows
        if row.promotion_price_with_vat is not None
    ]
    discounts = [
        row.promotion_discount_percent
        for row in rows
        if row.promotion_discount_percent is not None
    ]

    return {
        "matched": bool(action_ids or titles),
        "count": len(action_ids or titles),
        "action_ids": action_ids,
        "titles": titles,
        "price_with_vat": min(prices) if prices else None,
        "discount_percent": max(discounts) if discounts else None,
    }


def _same_optional_value(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None

    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None

    first = numeric_values[0]
    if all(abs(value - first) < 0.01 for value in numeric_values):
        return first

    return None


def _weighted_unit_expense(rows: list[OzonSkuEfficiencyRow]) -> float | None:
    if not all(row.matched_unit_economy for row in rows):
        return None

    unit_expense_total = _sum_optional_values(
        [
            row.profit_breakdown.unit_expense_total
            if row.profit_breakdown is not None
            else None
            for row in rows
        ]
    )
    orders = sum(
        row.profit_breakdown.orders
        if row.profit_breakdown is not None
        else row.sku_orders
        for row in rows
    )
    if unit_expense_total is None or orders <= 0:
        return None

    return unit_expense_total / orders


def _display_unit_expense(rows: list[OzonSkuEfficiencyRow]) -> float | None:
    same_unit_expense = _same_optional_value(
        [row.unit_expense_with_ozon_commission for row in rows]
    )
    if same_unit_expense is not None:
        return same_unit_expense

    weighted_unit_expense = _weighted_unit_expense(rows)
    if weighted_unit_expense is not None:
        return weighted_unit_expense

    known_unit_expenses = [
        row.unit_expense_with_ozon_commission
        for row in rows
        if row.unit_expense_with_ozon_commission is not None
    ]
    if not known_unit_expenses:
        return None

    return known_unit_expenses[-1]


def _row_unit_expense_for_total_sales(row: OzonSkuEfficiencyRow) -> float | None:
    if row.unit_expense_with_ozon_commission is not None:
        return row.unit_expense_with_ozon_commission

    if (
        row.profit_breakdown is not None
        and row.profit_breakdown.unit_expense_total is not None
        and row.profit_breakdown.orders > 0
    ):
        return row.profit_breakdown.unit_expense_total / row.profit_breakdown.orders

    return None


def _source_campaign_ids(raw_row: dict[str, str], fallback_campaign_id: str) -> list[str]:
    campaign_id = raw_row.get("__campaign_id")
    if campaign_id:
        return [campaign_id]

    return [fallback_campaign_id] if fallback_campaign_id != "ALL" else []


def _source_campaign_titles(raw_row: dict[str, str]) -> list[str]:
    campaign_title = raw_row.get("__campaign_title")
    return [campaign_title] if campaign_title else []


def _merge_string_lists(values: Iterable[Iterable[str]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for items in values:
        for item in items:
            if item in seen:
                continue

            seen.add(item)
            result.append(item)

    return result


def _normalize_match_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _build_total_sales_warning(
    response: OzonSkuEfficiencyResponse,
    rows: list[OzonSkuEfficiencyRow],
) -> str | None:
    messages: list[str] = []
    unmatched = [row.offer_id or row.sku for row in rows if not row.total_sales_matched]
    if unmatched:
        messages.append(
            "Не все рекламные SKU найдены в отчёте общих продаж: "
            + ", ".join(unmatched[:10])
        )
    if response.is_composite:
        messages.append(
            "Органика загружена агрегатом за весь период. Если период пересекает "
            "смену юнитки, себес органики рассчитан по среднему себесу рекламных "
            "заказов в сегментах. Для строгой точности нужен общий отчёт продаж "
            "по тем же сегментам дат."
        )

    return " ".join(messages) if messages else None


def _build_profit_breakdown(
    revenue_without_vat: float,
    ad_spend_without_vat: float,
    unit_expense_per_order: float | None,
    orders: int,
    profit_before_tax: float | None,
    tax_amount: float | None,
    net_profit: float | None,
    unit_expense_total: float | None = None,
    unit_economy_price_without_vat: float | None = None,
    unit_economy_profit_before_tax: float | None = None,
    unit_economy_net_profit: float | None = None,
) -> OzonSkuProfitBreakdown:
    calculated_unit_expense_total = (
        unit_expense_total
        if unit_expense_total is not None
        else unit_expense_per_order * orders
        if unit_expense_per_order is not None
        else None
    )
    revenue_without_vat_per_order = _safe_divide(revenue_without_vat, orders)
    ad_spend_without_vat_per_order = _safe_divide(ad_spend_without_vat, orders)
    profit_before_tax_per_order = (
        _safe_divide(profit_before_tax, orders)
        if profit_before_tax is not None
        else None
    )
    tax_amount_per_order = (
        _safe_divide(tax_amount, orders)
        if tax_amount is not None
        else None
    )
    net_profit_per_order = (
        _safe_divide(net_profit, orders)
        if net_profit is not None
        else None
    )

    if calculated_unit_expense_total is None:
        profit_formula = "Нет матчинга с юниткой: себес + комиссия неизвестны"
        profit_per_order_formula = "Нет матчинга с юниткой: расчёт на 1 заказ недоступен"
    else:
        profit_formula = (
            f"Выручка без НДС {_money(revenue_without_vat)} - "
            f"расход SKU по DRR {_money(ad_spend_without_vat)} - "
            f"себес + комиссия {_money(calculated_unit_expense_total)} = "
            f"{_money(profit_before_tax)}"
        )
        profit_per_order_formula = (
            f"На 1 заказ: выручка без НДС {_money(revenue_without_vat_per_order)} - "
            f"расход SKU по DRR {_money(ad_spend_without_vat_per_order)} - "
            f"себес + комиссия {_money(unit_expense_per_order)} = "
            f"{_money(profit_before_tax_per_order)}"
            if unit_expense_per_order is not None
            else "Итого: себес + комиссия показаны суммой по всем заказам"
        )

    net_formula = (
        f"Прибыль до налога {_money(profit_before_tax)} - "
        f"{PROFIT_TAX_LABEL} {_money(tax_amount)} = {_money(net_profit)}"
        if profit_before_tax is not None and tax_amount is not None
        else "Нет прибыли до налога: чистая прибыль не рассчитана"
    )
    net_per_order_formula = (
        f"На 1 заказ: прибыль до налога {_money(profit_before_tax_per_order)} - "
        f"{PROFIT_TAX_LABEL} {_money(tax_amount_per_order)} = "
        f"{_money(net_profit_per_order)}"
        if profit_before_tax_per_order is not None and tax_amount_per_order is not None
        else "Нет прибыли до налога на 1 заказ: чистая прибыль не рассчитана"
    )

    return OzonSkuProfitBreakdown(
        revenue_without_vat=revenue_without_vat,
        ad_spend_without_vat=ad_spend_without_vat,
        revenue_without_vat_per_order=revenue_without_vat_per_order,
        ad_spend_without_vat_per_order=ad_spend_without_vat_per_order,
        unit_expense_per_order=unit_expense_per_order,
        orders=orders,
        unit_expense_total=calculated_unit_expense_total,
        profit_before_tax=profit_before_tax,
        profit_before_tax_per_order=profit_before_tax_per_order,
        tax_rate=PROFIT_TAX_RATE,
        tax_amount=tax_amount,
        tax_amount_per_order=tax_amount_per_order,
        net_profit=net_profit,
        net_profit_per_order=net_profit_per_order,
        unit_economy_price_without_vat=unit_economy_price_without_vat,
        unit_economy_profit_before_tax=unit_economy_profit_before_tax,
        unit_economy_net_profit=unit_economy_net_profit,
        profit_before_tax_formula=profit_formula,
        profit_before_tax_per_order_formula=profit_per_order_formula,
        net_profit_formula=net_formula,
        net_profit_per_order_formula=net_per_order_formula,
    )


def _money(value: float | None) -> str:
    if value is None:
        return "—"

    return f"{round(value):,}".replace(",", " ") + " руб."
