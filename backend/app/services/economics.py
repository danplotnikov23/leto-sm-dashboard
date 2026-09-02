from math import isfinite

from app.domain.models import (
    DrrScenario,
    EconomicsBreakdown,
    EconomicsInput,
    FbsBatchScenario,
    RecommendationStatus,
    SupplierProduct,
)
from app.services.tariff_provider import TariffProvider


class EconomicsService:
    calculation_version = "unit-economics-v7-ozon-calculator-fbs-bands"
    drr_scenario_percents = (8.0, 10.0, 12.0, 15.0)

    def __init__(self, tariff_provider: TariffProvider | None = None) -> None:
        self.tariff_provider = tariff_provider or TariffProvider()

    def calculate(self, data: EconomicsInput) -> EconomicsBreakdown:
        product = data.product
        warnings: list[str] = []
        if data.sale_price_vat_included <= 0:
            warnings.append("Цена продажи должна быть больше нуля; расчет будет отрицательным.")
        if product.purchase_price_vat_included == 0:
            warnings.append("Закупочная цена равна нулю: проверьте прайс поставщика.")
        if product.stock is None:
            warnings.append("Остаток поставщика не указан: доступность товара не подтверждена.")
        elif product.stock <= 0:
            warnings.append("Остаток поставщика равен нулю: товар нельзя запускать до пополнения.")
        if product.weight_kg is None or product.dimensions.volume_liters is None:
            warnings.append("Нет полного веса/габаритов: логистика рассчитана по базовой оценке.")
        if data.seller_bonus_percent > 80:
            warnings.append("Начисление баллами выше 80% цены: проверьте отчет Ozon.")
        if data.ozon_visible_discount_percent >= 95:
            warnings.append("Видимая скидка Ozon слишком высокая: цена до скидки будет искажена.")

        tariff = self.tariff_provider.get_rule(product, data.sale_price_vat_included)
        if tariff.warning:
            warnings.append(tariff.warning)
        if data.tax_regime == "ip_usn_6" and data.use_vat:
            warnings.append(
                "Для ИП УСН 6% НДС обычно не применяется; проверьте налоговый сценарий."
            )

        vat_divider = 1 + data.vat_rate if data.use_vat else 1
        sale_ex_vat = data.sale_price_vat_included / vat_divider
        purchase_ex_vat = product.purchase_price_vat_included / vat_divider

        commission = data.sale_price_vat_included * tariff.commission_percent / 100
        logistics = self._logistics(data, tariff.fbs_logistics_base, tariff.fbo_logistics_base)
        acquiring = data.sale_price_vat_included * tariff.acquiring_percent / 100
        storage = self._storage(product, tariff.storage_per_liter_month)
        advertising = data.sale_price_vat_included * data.advertising_drr_percent / 100
        discount = data.sale_price_vat_included * data.discount_percent / 100
        ozon_bonus_accrual = data.sale_price_vat_included * data.seller_bonus_percent / 100
        partner_program_accrual = data.sale_price_vat_included * data.partner_program_percent / 100
        delivery_accrual = data.sale_price_vat_included * data.delivery_accrual_percent / 100
        list_price = self._price_before_visible_discount(data)
        customer_price_after_discount = max(data.sale_price_vat_included - discount, 0)
        bank_card_price = customer_price_after_discount * (
            1 - max(data.bank_card_discount_percent, 0) / 100
        )
        effective_customer_price_after_bonus = max(
            customer_price_after_discount - ozon_bonus_accrual,
            0,
        )
        buyer_payment_price = effective_customer_price_after_bonus
        marketplace_gross_accrual = (
            buyer_payment_price + ozon_bonus_accrual + partner_program_accrual + delivery_accrual
        )
        ozon_services_total = commission + logistics + acquiring + storage
        expected_payout_after_ozon_services = marketplace_gross_accrual - ozon_services_total

        revenue_basis = marketplace_gross_accrual / vat_divider
        profit_before_tax = (
            revenue_basis
            - purchase_ex_vat
            - commission
            - logistics
            - acquiring
            - data.package_cost
            - data.fulfillment_processing_cost
            - storage
            - advertising
            - discount
            - data.other_costs
        )
        usn_tax = 0.0
        usn_additional_contribution = 0.0
        profit_tax = 0.0
        if data.tax_regime == "ip_usn_6":
            tax_income_basis = marketplace_gross_accrual
            usn_tax = tax_income_basis * data.usn_tax_rate
            if data.apply_usn_additional_contribution:
                usn_additional_contribution = (
                    tax_income_basis * data.usn_additional_contribution_rate
                )
            profit_tax = usn_tax + usn_additional_contribution
        else:
            tax_income_basis = profit_before_tax
            profit_tax = max(profit_before_tax, 0) * data.profit_tax_rate
        tax_only_break_even = self._tax_only_break_even_price(
            data,
            product.purchase_price_vat_included,
        )
        net_profit = profit_before_tax - profit_tax
        fast_payout_fee = marketplace_gross_accrual * data.fast_payout_fee_percent / 100
        designer_content_cost = marketplace_gross_accrual * data.designer_content_percent / 100
        business_fulfillment_pickup_cost = (
            marketplace_gross_accrual * data.business_fulfillment_pickup_percent / 100
        )
        business_extra_costs_total = (
            fast_payout_fee + designer_content_cost + business_fulfillment_pickup_cost
        )
        business_net_profit = net_profit - business_extra_costs_total
        business_margin = (
            business_net_profit / data.sale_price_vat_included * 100
            if data.sale_price_vat_included
            else 0.0
        )
        target_business_profit = data.sale_price_vat_included * data.target_margin_percent / 100
        max_purchase_break_even_raw = (
            product.purchase_price_vat_included + business_net_profit * vat_divider
        )
        target_purchase_price_raw = (
            product.purchase_price_vat_included
            + (business_net_profit - target_business_profit) * vat_divider
        )
        max_purchase_break_even = max(max_purchase_break_even_raw, 0.0)
        target_purchase_price = max(target_purchase_price_raw, 0.0)
        break_even_supplier_discount = max(
            product.purchase_price_vat_included - max_purchase_break_even,
            0.0,
        )
        target_supplier_discount = max(
            product.purchase_price_vat_included - target_purchase_price,
            0.0,
        )
        break_even_supplier_discount_percent = (
            break_even_supplier_discount / product.purchase_price_vat_included * 100
            if product.purchase_price_vat_included
            else 0.0
        )
        target_supplier_discount_percent = (
            target_supplier_discount / product.purchase_price_vat_included * 100
            if product.purchase_price_vat_included
            else 0.0
        )
        margin = (
            net_profit / data.sale_price_vat_included * 100 if data.sale_price_vat_included else 0.0
        )
        markup = (sale_ex_vat - purchase_ex_vat) / purchase_ex_vat * 100 if purchase_ex_vat else 0.0
        cost_basis_without_commission = (
            purchase_ex_vat
            + logistics
            + acquiring
            + data.package_cost
            + data.fulfillment_processing_cost
            + storage
            + data.other_costs
        )
        cost_basis_with_commission = cost_basis_without_commission + commission
        total_expenses_before_tax = (
            purchase_ex_vat
            + commission
            + logistics
            + acquiring
            + data.package_cost
            + data.fulfillment_processing_cost
            + storage
            + advertising
            + discount
            + data.other_costs
        )
        expense_shares_percent = {
            "purchase": self._share_percent(purchase_ex_vat, marketplace_gross_accrual),
            "commission": self._share_percent(commission, marketplace_gross_accrual),
            "logistics": self._share_percent(logistics, marketplace_gross_accrual),
            "acquiring": self._share_percent(acquiring, marketplace_gross_accrual),
            "package": self._share_percent(data.package_cost, marketplace_gross_accrual),
            "fulfillment_processing": self._share_percent(
                data.fulfillment_processing_cost,
                marketplace_gross_accrual,
            ),
            "storage": self._share_percent(storage, marketplace_gross_accrual),
            "ozon_services": self._share_percent(
                ozon_services_total,
                marketplace_gross_accrual,
            ),
            "expenses_before_tax": self._share_percent(
                total_expenses_before_tax,
                marketplace_gross_accrual,
            ),
            "taxes": self._share_percent(profit_tax, marketplace_gross_accrual),
            "business_extra": self._share_percent(
                business_extra_costs_total,
                marketplace_gross_accrual,
            ),
            "net_profit": self._share_percent(net_profit, marketplace_gross_accrual),
            "business_net_profit": self._share_percent(
                business_net_profit,
                marketplace_gross_accrual,
            ),
        }

        break_even = self._break_even_price(
            data,
            product,
            logistics,
            storage,
            target_margin_percent=0.0,
        )
        recommended = self._break_even_price(
            data,
            product,
            logistics,
            storage,
            target_margin_percent=data.target_margin_percent,
        )
        competitor_min = data.competitor.min_price if data.competitor else None
        estimated_competitor = competitor_min or self._estimated_competitor_price(
            product,
            recommended,
        )
        competitiveness_gap = (
            round(data.sale_price_vat_included - estimated_competitor, 2)
            if estimated_competitor is not None
            else None
        )
        recommendation = self._recommend(
            net_profit,
            margin,
            data,
            break_even,
            competitor_min,
            warnings,
        )
        drr_scenarios = self._drr_scenarios(
            data,
            product,
            tariff.commission_percent,
            tariff.acquiring_percent,
            logistics,
            storage,
            revenue_basis,
            purchase_ex_vat,
            commission,
            acquiring,
            discount,
            break_even,
            estimated_competitor,
            warnings,
        )
        fbs_batch_scenarios = self._fbs_batch_scenarios(data, business_net_profit)

        return EconomicsBreakdown(
            product_id=product.id,
            calculation_version=self.calculation_version,
            source=tariff.source,
            tax_regime=data.tax_regime,
            vat_applicable=data.use_vat,
            vat_rate=round(data.vat_rate, 4),
            tax_income_basis=round(tax_income_basis, 2),
            tax_only_break_even_price_vat_included=round(tax_only_break_even, 2),
            list_price_vat_included=round(list_price, 2),
            ozon_price_before_discount_vat_included=round(list_price, 2),
            ozon_visible_discount_percent=round(data.ozon_visible_discount_percent, 2),
            real_fbs_price_vat_included=round(customer_price_after_discount, 2),
            bank_card_price_vat_included=round(bank_card_price, 2),
            bank_card_discount_percent=round(data.bank_card_discount_percent, 2),
            ozon_min_price_vat_included=round(
                max(break_even, data.sale_price_vat_included * 0.92),
                2,
            ),
            customer_price_after_discount=round(customer_price_after_discount, 2),
            effective_customer_price_after_bonus=round(effective_customer_price_after_bonus, 2),
            buyer_payment_price_vat_included=round(buyer_payment_price, 2),
            ozon_bonus_accrual=round(ozon_bonus_accrual, 2),
            partner_program_accrual=round(partner_program_accrual, 2),
            delivery_accrual=round(delivery_accrual, 2),
            marketplace_gross_accrual_vat_included=round(marketplace_gross_accrual, 2),
            ozon_services_total=round(ozon_services_total, 2),
            expected_payout_after_ozon_services=round(
                expected_payout_after_ozon_services,
                2,
            ),
            estimated_competitor_price_vat_included=(
                round(estimated_competitor, 2) if estimated_competitor is not None else None
            ),
            sale_price_vat_included=round(data.sale_price_vat_included, 2),
            sale_price_vat_excluded=round(sale_ex_vat, 2),
            purchase_price_vat_included=round(product.purchase_price_vat_included, 2),
            purchase_price_vat_excluded=round(purchase_ex_vat, 2),
            ozon_commission_percent=round(tariff.commission_percent, 2),
            commission_source_label=tariff.commission_source_label,
            matched_ozon_category=tariff.matched_ozon_category,
            matched_ozon_product_type=tariff.matched_ozon_product_type,
            ozon_commission=round(commission, 2),
            logistics=round(logistics, 2),
            acquiring=round(acquiring, 2),
            package_cost=round(data.package_cost, 2),
            fulfillment_processing_cost=round(data.fulfillment_processing_cost, 2),
            storage=round(storage, 2),
            advertising=round(advertising, 2),
            advertising_drr_percent=round(data.advertising_drr_percent, 2),
            discount=round(discount, 2),
            seller_bonus_points=round(ozon_bonus_accrual, 2),
            seller_bonus_percent=round(data.seller_bonus_percent, 2),
            seller_bonus_max_spend_percent=80.0,
            other_costs=round(data.other_costs, 2),
            profit_before_tax=round(profit_before_tax, 2),
            usn_tax=round(usn_tax, 2),
            usn_additional_contribution=round(usn_additional_contribution, 2),
            profit_tax=round(profit_tax, 2),
            net_profit=round(net_profit, 2),
            fast_payout_fee_percent=round(data.fast_payout_fee_percent, 2),
            fast_payout_fee=round(fast_payout_fee, 2),
            designer_content_percent=round(data.designer_content_percent, 2),
            designer_content_cost=round(designer_content_cost, 2),
            business_fulfillment_pickup_percent=round(
                data.business_fulfillment_pickup_percent,
                2,
            ),
            business_fulfillment_pickup_cost=round(business_fulfillment_pickup_cost, 2),
            business_extra_costs_total=round(business_extra_costs_total, 2),
            business_net_profit=round(business_net_profit, 2),
            business_margin_percent=round(business_margin, 2),
            target_margin_percent=round(data.target_margin_percent, 2),
            target_business_profit=round(target_business_profit, 2),
            max_purchase_price_break_even_vat_included=round(
                max_purchase_break_even,
                2,
            ),
            supplier_discount_break_even_feasible=max_purchase_break_even_raw >= 0,
            required_supplier_discount_break_even_amount=round(
                break_even_supplier_discount,
                2,
            ),
            required_supplier_discount_break_even_percent=round(
                break_even_supplier_discount_percent,
                2,
            ),
            target_purchase_price_vat_included=round(target_purchase_price, 2),
            supplier_discount_target_feasible=target_purchase_price_raw >= 0,
            required_supplier_discount_target_amount=round(
                target_supplier_discount,
                2,
            ),
            required_supplier_discount_target_percent=round(
                target_supplier_discount_percent,
                2,
            ),
            expense_shares_percent=expense_shares_percent,
            margin_percent=round(margin, 2),
            markup_percent=round(markup, 2),
            cost_basis_without_commission=round(cost_basis_without_commission, 2),
            cost_basis_with_commission=round(cost_basis_with_commission, 2),
            total_expenses_before_tax=round(total_expenses_before_tax, 2),
            break_even_price_vat_included=round(break_even, 2),
            recommended_price_vat_included=round(recommended, 2),
            competitiveness_gap=competitiveness_gap,
            recommendation=recommendation,
            drr_scenarios=drr_scenarios,
            fbs_batch_scenarios=fbs_batch_scenarios,
            warnings=warnings,
            formula=self._formula(data, tariff.commission_percent, tariff.acquiring_percent),
        )

    @staticmethod
    def _share_percent(value: float, basis: float) -> float:
        return round(value / basis * 100, 2) if basis else 0.0

    def _price_before_visible_discount(self, data: EconomicsInput) -> float:
        visible_discount_rate = max(min(data.ozon_visible_discount_percent / 100, 0.95), 0)
        if visible_discount_rate == 0:
            return data.sale_price_vat_included
        return data.sale_price_vat_included / (1 - visible_discount_rate)

    def _tax_only_break_even_price(self, data: EconomicsInput, purchase_price: float) -> float:
        if data.tax_regime != "ip_usn_6":
            return purchase_price
        tax_rate = data.usn_tax_rate
        if data.apply_usn_additional_contribution:
            tax_rate += data.usn_additional_contribution_rate
        if tax_rate >= 1:
            return float("inf")
        return purchase_price / (1 - tax_rate)

    def _logistics(self, data: EconomicsInput, fbs_base: float, fbo_base: float) -> float:
        volume = data.product.dimensions.volume_liters or 1.0
        weight = data.product.weight_kg or 1.0
        if data.fulfillment_model == "fbo":
            return fbo_base + max(volume - 1, 0) * 3.5 + max(weight - 1, 0) * 18
        if volume <= 1:
            return fbs_base
        if volume <= 3:
            # Official calculator export, 17.06.2026, 2.7555 l / 0.81 kg:
            # processing 30 + logistics 84 + delivery to pickup point 25.
            return 139.0
        return 139.0 + max(volume - 3, 0) * 10 + max(weight - 1, 0) * 18

    def _storage(self, product: SupplierProduct, rate: float) -> float:
        if product.dimensions.volume_liters is None:
            return 0.0
        return product.dimensions.volume_liters * rate

    def _break_even_price(
        self,
        data: EconomicsInput,
        product: SupplierProduct,
        logistics: float,
        storage: float,
        target_margin_percent: float,
    ) -> float:
        vat_divider = 1 + data.vat_rate if data.use_vat else 1
        gross_accrual_rate = (
            1
            - data.discount_percent / 100
            + data.partner_program_percent / 100
            + data.delivery_accrual_percent / 100
        )
        tax_rate = 0.0
        if data.tax_regime == "ip_usn_6":
            tax_rate = data.usn_tax_rate
            if data.apply_usn_additional_contribution:
                tax_rate += data.usn_additional_contribution_rate
        business_extra_rate = (
            data.fast_payout_fee_percent
            + data.designer_content_percent
            + data.business_fulfillment_pickup_percent
        ) / 100
        fixed_costs = (
            product.purchase_price_vat_included / vat_divider
            + logistics
            + data.package_cost
            + data.fulfillment_processing_cost
            + storage
            + data.other_costs
        )
        candidate = max(data.sale_price_vat_included, product.purchase_price_vat_included)
        for _ in range(5):
            tariff = self.tariff_provider.get_rule(product, candidate)
            variable_rate = (
                gross_accrual_rate / vat_divider
                - tariff.commission_percent / 100
                - tariff.acquiring_percent / 100
                - data.advertising_drr_percent / 100
                - data.discount_percent / 100
                - gross_accrual_rate * tax_rate
                - gross_accrual_rate * business_extra_rate
                - target_margin_percent / 100
            )
            if variable_rate <= 0 or not isfinite(variable_rate):
                return float("inf")
            candidate = fixed_costs / variable_rate
        return candidate

    def _estimated_competitor_price(
        self,
        product: SupplierProduct,
        recommended_price: float,
    ) -> float | None:
        if not isfinite(recommended_price):
            return None
        category = (product.category or "").lower()
        multiplier = 0.97
        if any(token in category for token in ("электр", "свет", "ламп", "бра")):
            multiplier = 0.94
        if any(token in category for token in ("смесь", "цемент", "клей", "штукатур")):
            multiplier = 0.98
        return max(product.purchase_price_vat_included * 1.15, recommended_price * multiplier)

    def _drr_scenarios(
        self,
        data: EconomicsInput,
        product: SupplierProduct,
        commission_percent: float,
        acquiring_percent: float,
        logistics: float,
        storage: float,
        revenue_basis: float,
        purchase_ex_vat: float,
        commission: float,
        acquiring: float,
        discount: float,
        current_break_even: float,
        competitor_min: float | None,
        warnings: list[str],
    ) -> list[DrrScenario]:
        scenarios: list[DrrScenario] = []
        for drr in self.drr_scenario_percents:
            advertising = data.sale_price_vat_included * drr / 100
            scenario_ozon_bonus_accrual = (
                data.sale_price_vat_included * data.seller_bonus_percent / 100
            )
            scenario_partner_program_accrual = (
                data.sale_price_vat_included * data.partner_program_percent / 100
            )
            scenario_delivery_accrual = (
                data.sale_price_vat_included * data.delivery_accrual_percent / 100
            )
            scenario_customer_price_after_discount = max(
                data.sale_price_vat_included - discount,
                0,
            )
            scenario_buyer_payment_price = max(
                scenario_customer_price_after_discount - scenario_ozon_bonus_accrual,
                0,
            )
            scenario_gross_accrual = (
                scenario_buyer_payment_price
                + scenario_ozon_bonus_accrual
                + scenario_partner_program_accrual
                + scenario_delivery_accrual
            )
            profit_before_tax = (
                revenue_basis
                - purchase_ex_vat
                - commission
                - logistics
                - acquiring
                - data.package_cost
                - data.fulfillment_processing_cost
                - storage
                - advertising
                - discount
                - data.other_costs
            )
            if data.tax_regime == "ip_usn_6":
                profit_tax = scenario_gross_accrual * data.usn_tax_rate
                if data.apply_usn_additional_contribution:
                    profit_tax += scenario_gross_accrual * data.usn_additional_contribution_rate
            else:
                profit_tax = max(profit_before_tax, 0) * data.profit_tax_rate
            net_profit = profit_before_tax - profit_tax
            fast_payout_fee = scenario_gross_accrual * data.fast_payout_fee_percent / 100
            designer_content_cost = scenario_gross_accrual * data.designer_content_percent / 100
            business_fulfillment_pickup_cost = (
                scenario_gross_accrual * data.business_fulfillment_pickup_percent / 100
            )
            business_extra_costs_total = (
                fast_payout_fee + designer_content_cost + business_fulfillment_pickup_cost
            )
            business_net_profit = net_profit - business_extra_costs_total
            margin = (
                net_profit / data.sale_price_vat_included * 100
                if data.sale_price_vat_included
                else 0.0
            )
            scenario_input = data.model_copy(update={"advertising_drr_percent": drr})
            break_even = self._break_even_price(
                scenario_input,
                product,
                logistics,
                storage,
                target_margin_percent=0.0,
            )
            scenarios.append(
                DrrScenario(
                    drr_percent=drr,
                    advertising=round(advertising, 2),
                    profit_before_tax=round(profit_before_tax, 2),
                    profit_tax=round(profit_tax, 2),
                    net_profit=round(net_profit, 2),
                    fast_payout_fee_percent=round(data.fast_payout_fee_percent, 2),
                    fast_payout_fee=round(fast_payout_fee, 2),
                    designer_content_percent=round(data.designer_content_percent, 2),
                    designer_content_cost=round(designer_content_cost, 2),
                    business_fulfillment_pickup_percent=round(
                        data.business_fulfillment_pickup_percent,
                        2,
                    ),
                    business_fulfillment_pickup_cost=round(
                        business_fulfillment_pickup_cost,
                        2,
                    ),
                    business_extra_costs_total=round(business_extra_costs_total, 2),
                    business_net_profit=round(business_net_profit, 2),
                    margin_percent=round(margin, 2),
                    break_even_price_vat_included=round(break_even, 2),
                    recommendation=self._recommend(
                        net_profit,
                        margin,
                        scenario_input,
                        break_even if isfinite(break_even) else current_break_even,
                        competitor_min,
                        warnings,
                    ),
                )
            )
        return scenarios

    def _fbs_batch_scenarios(
        self,
        data: EconomicsInput,
        business_net_profit: float,
    ) -> list[FbsBatchScenario]:
        scenarios: list[FbsBatchScenario] = []
        fixed_costs_total = (
            data.fbs_supplier_pickup_daily_cost + data.fbs_ozon_sc_delivery_daily_cost
        )
        seen_order_counts: set[int] = set()
        for orders_per_day in data.fbs_orders_per_day_scenarios:
            if orders_per_day <= 0 or orders_per_day in seen_order_counts:
                continue
            seen_order_counts.add(orders_per_day)
            allocated_cost = fixed_costs_total / orders_per_day
            profit_after_fixed = business_net_profit - allocated_cost
            margin = (
                profit_after_fixed / data.sale_price_vat_included * 100
                if data.sale_price_vat_included
                else 0.0
            )
            scenarios.append(
                FbsBatchScenario(
                    orders_per_day=orders_per_day,
                    supplier_pickup_daily_cost=round(data.fbs_supplier_pickup_daily_cost, 2),
                    ozon_sc_delivery_daily_cost=round(data.fbs_ozon_sc_delivery_daily_cost, 2),
                    fixed_costs_total=round(fixed_costs_total, 2),
                    allocated_fixed_cost_per_order=round(allocated_cost, 2),
                    business_net_profit_after_fixed=round(profit_after_fixed, 2),
                    margin_percent=round(margin, 2),
                    recommendation=self._recommend_after_fixed_batch(
                        data,
                        profit_after_fixed,
                        margin,
                    ),
                )
            )
        return scenarios

    def _recommend_after_fixed_batch(
        self,
        data: EconomicsInput,
        profit_after_fixed: float,
        margin: float,
    ) -> RecommendationStatus:
        if data.product.stock is None:
            return RecommendationStatus.MANUAL_REVIEW
        if data.product.stock <= 0:
            return RecommendationStatus.DO_NOT_LIST
        if profit_after_fixed <= 0:
            return RecommendationStatus.DO_NOT_LIST
        if margin >= data.target_margin_percent:
            return RecommendationStatus.LIST
        if margin >= max(data.target_margin_percent * 0.5, 5):
            return RecommendationStatus.LIST_CAREFULLY
        return RecommendationStatus.PRICE_UP_ONLY

    def _recommend(
        self,
        net_profit: float,
        margin: float,
        data: EconomicsInput,
        break_even: float,
        competitor_min: float | None,
        warnings: list[str],
    ) -> RecommendationStatus:
        if data.product.stock is None:
            return RecommendationStatus.MANUAL_REVIEW
        if data.product.stock <= 0:
            return RecommendationStatus.DO_NOT_LIST
        if warnings and (data.product.category is None or data.product.category == ""):
            return RecommendationStatus.MANUAL_REVIEW
        if net_profit < 0:
            if data.discount_percent > 0:
                return RecommendationStatus.NO_PROMO_ONLY
            if data.sale_price_vat_included < break_even:
                return RecommendationStatus.PRICE_UP_ONLY
            return RecommendationStatus.DO_NOT_LIST
        if competitor_min is not None and competitor_min < break_even:
            return RecommendationStatus.DO_NOT_LIST
        if margin >= data.target_margin_percent:
            return RecommendationStatus.LIST
        if margin >= max(data.target_margin_percent * 0.5, 5):
            return RecommendationStatus.LIST_CAREFULLY
        return RecommendationStatus.PRICE_UP_ONLY

    def _formula(
        self,
        data: EconomicsInput,
        commission_percent: float,
        acquiring_percent: float,
    ) -> list[str]:
        return [
            (
                "marketplace_gross_accrual = buyer_payment + ozon_bonus_accrual "
                "+ partner_program + delivery_accrual"
            ),
            (
                "expected_payout_after_ozon_services = marketplace_gross_accrual "
                "- commission - logistics - acquiring - storage"
            ),
            "revenue_without_vat = marketplace_gross_accrual / (1 + vat_rate)",
            (
                "profit_before_tax = revenue_without_vat - purchase_without_vat "
                "- commission - logistics - acquiring - package - fulfillment - storage "
                "- advertising - discount - other_costs"
            ),
            "ip_usn_tax = marketplace_gross_accrual * 6%, если режим ИП УСН Доходы",
            (
                "ip_1_percent = marketplace_gross_accrual * 1%, "
                "как оценка после превышения 300 000 ₽ дохода в год"
            ),
            "tax_only_floor = purchase_price / (1 - 7%) для ИП УСН 6% + 1%",
            "osno_profit_tax = max(profit_before_tax, 0) * profit_tax_rate",
            "net_profit = profit_before_tax - profit_tax",
            (
                "business_extra_costs_total = marketplace_gross_accrual * "
                f"({data.fast_payout_fee_percent}% + {data.designer_content_percent}% "
                f"+ {data.business_fulfillment_pickup_percent}%)"
            ),
            "business_net_profit = net_profit - business_extra_costs_total",
            (
                "fbs_batch_fixed_cost_per_order = "
                f"({data.fbs_supplier_pickup_daily_cost} pickup + "
                f"{data.fbs_ozon_sc_delivery_daily_cost} Ozon SC delivery) / orders_per_day"
            ),
            (
                "fbs_batch_business_net_profit = business_net_profit "
                "- fbs_batch_fixed_cost_per_order"
            ),
            f"commission = sale_price * {commission_percent}%",
            f"acquiring = sale_price * {acquiring_percent}%",
            f"discount = sale_price * {data.discount_percent}%",
            (
                "ozon_price_before_discount = real_fbs_price / "
                f"(1 - visible_discount {data.ozon_visible_discount_percent}%)"
            ),
            (
                f"bank_card_price = real_fbs_price * (1 - card_discount "
                f"{data.bank_card_discount_percent}%), не расход продавца без подтверждения Ozon"
            ),
            (
                f"ozon_bonus_accrual = sale_price * {data.seller_bonus_percent}%, "
                "это начисление из отчета Ozon, а не расход продавца"
            ),
            f"partner_program = sale_price * {data.partner_program_percent}%",
            f"delivery_accrual = sale_price * {data.delivery_accrual_percent}%",
            f"advertising = sale_price * DRR {data.advertising_drr_percent}%",
            f"fulfillment_processing = {data.fulfillment_processing_cost} руб.",
        ]
