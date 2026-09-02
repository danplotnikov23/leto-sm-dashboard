from app.domain.models import Dimensions, EconomicsInput, RecommendationStatus, SupplierProduct
from app.services.economics import EconomicsService


def product(
    price: float = 1000,
    category: str | None = "Стройматериалы",
    stock: float | None = 10,
) -> SupplierProduct:
    return SupplierProduct(
        supplier_article="A-1",
        title="Клей плиточный",
        category=category,
        purchase_price_vat_included=price,
        weight_kg=25,
        stock=stock,
        dimensions=Dimensions(length_cm=40, width_cm=30, height_cm=10),
    )


def test_ip_usn_tax_is_applied_to_income_even_when_unit_is_loss() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(product=product(1200), sale_price_vat_included=900)
    )

    assert result.profit_before_tax < 0
    assert result.tax_regime == "ip_usn_6"
    assert result.usn_tax > 0
    assert result.usn_additional_contribution > 0
    assert result.profit_tax == result.usn_tax + result.usn_additional_contribution
    assert result.recommendation in {
        RecommendationStatus.PRICE_UP_ONLY,
        RecommendationStatus.DO_NOT_LIST,
        RecommendationStatus.NO_PROMO_ONLY,
    }


def test_osno_profit_tax_is_not_applied_to_loss() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(1200),
            sale_price_vat_included=900,
            tax_regime="osno",
            use_vat=True,
        )
    )

    assert result.profit_before_tax < 0
    assert result.profit_tax == 0


def test_zero_purchase_price_is_warned_but_not_crashing() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(product=product(0), sale_price_vat_included=1500)
    )

    assert isinstance(result.net_profit, float)
    assert any("Закупочная цена равна нулю" in warning for warning in result.warnings)


def test_stock_availability_controls_recommendation() -> None:
    unavailable = EconomicsService().calculate(
        EconomicsInput(product=product(500, stock=0), sale_price_vat_included=2000)
    )
    unknown = EconomicsService().calculate(
        EconomicsInput(product=product(500, stock=None), sale_price_vat_included=2000)
    )

    assert unavailable.recommendation == RecommendationStatus.DO_NOT_LIST
    assert any("равен нулю" in warning for warning in unavailable.warnings)
    assert unknown.recommendation == RecommendationStatus.MANUAL_REVIEW
    assert any("не указан" in warning for warning in unknown.warnings)


def test_unknown_category_uses_estimate_warning() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(product=product(500, category=None), sale_price_vat_included=1200)
    )

    assert result.source == "estimate"
    assert any("Тип товара не сопоставлен" in warning for warning in result.warnings)


def test_ozon_bonus_accrual_is_separate_from_discount() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=1400,
            discount_percent=10,
            seller_bonus_percent=5,
        )
    )

    assert result.discount == 140
    assert result.seller_bonus_points == 70
    assert result.ozon_bonus_accrual == 70
    assert result.marketplace_gross_accrual_vat_included > result.buyer_payment_price_vat_included
    assert result.expected_payout_after_ozon_services == round(
        result.marketplace_gross_accrual_vat_included - result.ozon_services_total,
        2,
    )
    assert any("ozon_bonus_accrual" in line for line in result.formula)


def test_customer_price_and_expected_payout_are_explicit() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=2000,
            seller_bonus_percent=25,
            partner_program_percent=1,
        )
    )

    assert result.real_fbs_price_vat_included == 2000
    assert result.buyer_payment_price_vat_included == 1500
    assert result.ozon_bonus_accrual == 500
    assert result.marketplace_gross_accrual_vat_included == 2020
    assert (
        result.expected_payout_after_ozon_services < result.marketplace_gross_accrual_vat_included
    )
    assert any("expected_payout_after_ozon_services" in line for line in result.formula)


def test_business_extra_costs_use_total_accruals_without_changing_ozon_profit() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=2000,
            seller_bonus_percent=25,
            partner_program_percent=1,
            business_fulfillment_pickup_percent=5,
        )
    )

    original_net_profit = result.net_profit

    assert result.marketplace_gross_accrual_vat_included == 2020
    assert result.fast_payout_fee == 49.49
    assert result.designer_content_cost == 80.8
    assert result.business_fulfillment_pickup_cost == 101
    assert result.business_extra_costs_total == 231.29
    assert result.business_net_profit == round(original_net_profit - 231.29, 2)
    assert any("business_net_profit" in line for line in result.formula)


def test_business_fulfillment_reserve_is_disabled_by_default() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(product=product(500), sale_price_vat_included=2000)
    )

    assert result.business_fulfillment_pickup_percent == 0
    assert result.business_fulfillment_pickup_cost == 0


def test_official_fbs_commission_uses_product_type_and_price_band() -> None:
    nails = SupplierProduct(
        supplier_article="NAILS-1",
        title="Гвозди строительные 2х40",
        category="Гвозди",
        purchase_price_vat_included=39,
    )
    result = EconomicsService().calculate(
        EconomicsInput(product=nails, sale_price_vat_included=539)
    )

    assert result.source == "excel"
    assert result.matched_ozon_product_type == "Гвозди"
    assert result.ozon_commission_percent == 48
    assert result.ozon_commission == 258.72


def test_fum_tape_matches_official_calculator_small_fbs_costs() -> None:
    tape = SupplierProduct(
        supplier_article="02921",
        title="Лента ФУМ 12мм, 0,1мм*10м",
        category="Уплотнительные и резинотехнические изделия",
        purchase_price_vat_included=12,
        weight_kg=0.02,
        dimensions=Dimensions(length_cm=6, width_cm=6, height_cm=4),
    )
    result = EconomicsService().calculate(EconomicsInput(product=tape, sale_price_vat_included=80))

    assert result.matched_ozon_product_type == "Лента ФУМ"
    assert result.ozon_commission_percent == 14
    assert result.logistics == 63
    assert result.ozon_services_total == 75
    assert result.expected_payout_after_ozon_services == 5.4


def test_siphon_matches_official_calculator_commission_and_fbs_costs() -> None:
    siphon = SupplierProduct(
        supplier_article="HB80",
        title="Сифон для умывальника Haiba без выпуска HB80, хром",
        category="Сифон сливной",
        purchase_price_vat_included=1053,
        weight_kg=0.81,
        dimensions=Dimensions(length_cm=19, width_cm=15, height_cm=9.668421),
    )
    result = EconomicsService().calculate(
        EconomicsInput(product=siphon, sale_price_vat_included=2685)
    )

    assert result.matched_ozon_product_type == "Сифон сливной"
    assert result.ozon_commission_percent == 46
    assert result.ozon_commission == 1235.1
    assert result.acquiring == 26.85
    assert result.logistics == 139


def test_fulfillment_processing_is_not_counted_as_ozon_service() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=2000,
            fulfillment_processing_cost=90,
        )
    )

    assert result.ozon_services_total == round(
        result.ozon_commission + result.logistics + result.acquiring + result.storage,
        2,
    )
    assert result.fulfillment_processing_cost == 90


def test_business_break_even_and_target_margin_prices_recalculate_full_business_profit() -> None:
    service = EconomicsService()
    base_input = EconomicsInput(product=product(500), sale_price_vat_included=1200)
    result = service.calculate(base_input)

    at_break_even = service.calculate(
        base_input.model_copy(
            update={"sale_price_vat_included": result.break_even_price_vat_included}
        )
    )
    at_target_margin = service.calculate(
        base_input.model_copy(
            update={"sale_price_vat_included": result.recommended_price_vat_included}
        )
    )

    assert abs(at_break_even.business_net_profit) < 0.1
    assert abs(at_target_margin.business_margin_percent - 15) < 0.1


def test_supplier_discount_target_produces_target_margin_at_current_sale_price() -> None:
    service = EconomicsService()
    base_input = EconomicsInput(product=product(500), sale_price_vat_included=10_000)
    result = service.calculate(base_input)
    negotiated_product = base_input.product.model_copy(
        update={
            "purchase_price_vat_included": result.target_purchase_price_vat_included,
        }
    )
    negotiated = service.calculate(base_input.model_copy(update={"product": negotiated_product}))

    assert result.required_supplier_discount_target_amount >= 0
    assert result.required_supplier_discount_target_percent >= 0
    assert result.supplier_discount_target_feasible is True
    assert abs(negotiated.business_margin_percent - 15) < 0.1


def test_supplier_discount_is_marked_impossible_when_free_purchase_is_not_enough() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(product=product(500), sale_price_vat_included=1200)
    )

    assert result.target_purchase_price_vat_included == 0
    assert result.supplier_discount_target_feasible is False


def test_fbs_daily_fixed_costs_are_shown_as_batch_scenarios() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=2000,
            fbs_supplier_pickup_daily_cost=2500,
            fbs_ozon_sc_delivery_daily_cost=600,
            fbs_orders_per_day_scenarios=[1, 10, 20],
        )
    )

    scenarios = {scenario.orders_per_day: scenario for scenario in result.fbs_batch_scenarios}

    assert scenarios[1].fixed_costs_total == 3100
    assert scenarios[1].allocated_fixed_cost_per_order == 3100
    assert scenarios[10].allocated_fixed_cost_per_order == 310
    assert scenarios[20].allocated_fixed_cost_per_order == 155
    assert scenarios[10].business_net_profit_after_fixed == round(
        result.business_net_profit - 310, 2
    )
    assert any("fbs_batch_fixed_cost_per_order" in line for line in result.formula)


def test_unusually_high_ozon_bonus_accrual_is_warned() -> None:
    result = EconomicsService().calculate(
        EconomicsInput(
            product=product(500),
            sale_price_vat_included=1400,
            seller_bonus_percent=85,
        )
    )

    assert any("80%" in warning for warning in result.warnings)
