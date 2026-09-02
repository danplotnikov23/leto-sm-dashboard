"""Расчётный движок «живой» Юнитки — 1-в-1 порт формул листа `15.06.26`.

Каждая функция считает ОДИН столбец и в докстринге цитирует точную исходную формулу
Excel (взято из реальной книги `Юнитка Лето СМ.xlsx`, строка 3, 2026-09-02). Это не
переизобретённая бизнес-логика — прямой перенос, чтобы сверка была возможна визуально,
ячейка за ячейкой.

Проверка (см. `tests/test_unitka_engine.py`): значения сверены вручную по трём реальным
строкам, включая два независимых перекрёстных признака корректности —
рентабельность SKU №1 выходит ≈5.00% (совпадает с именем бэкапа
`..._before_S_5pct_margin.xlsx`, т.е. цена S была осознанно подобрана под целевую
маржу 5%), и AW3 (логистика по объёму, справочно) почти точно совпадает с Z3
(FBS затраты, ручной ввод) — похоже, Z изначально скопировали из AW.

ВАЖНО про допущения: в оригинальной книге ставки-допущения ($AB$1, $AF$1 и т.д.)
общие на ВСЮ таблицу (одна строка допущений на весь лист). Здесь то же самое —
`UnitkaAssumptions` передаётся один раз на всю сверку, не хранится в каждой строке.
"""

from __future__ import annotations

import re

from app.domain.unitka import UnitkaAssumptions, UnitkaRow, UnitkaRowComputed

_DIMENSIONS_RE = re.compile(r"^\s*≈?\s*([\d.,]+)\s*[×xX]\s*([\d.,]+)\s*[×xX]\s*([\d.,]+)\s*$")


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_volume_liters(dimensions_mm: str | None) -> float | None:
    """AV: =VALUE(SUBSTITUTE(LEFT(O3,FIND("×",O3)-1),"≈",""))*VALUE(MID(...))*VALUE(MID(...))/1000000

    Формула Excel режет строку "1050×440×1050" (Ш×В×Г, мм) по разделителю "×" на три
    числа и делит произведение на 1_000_000, чтобы перевести мм³ в литры. "≈" убирается
    только у ПЕРВОГО числа в оригинальной формуле — здесь для надёжности убираем у всех
    трёх (тот же результат для всех реальных строк, но безопаснее при неаккуратном вводе).
    """
    if not dimensions_mm:
        return None
    match = _DIMENSIONS_RE.match(dimensions_mm)
    if not match:
        return None
    try:
        w, h, d = (_parse_number(g) for g in match.groups())
    except ValueError:
        return None
    return round(w * h * d / 1_000_000, 6)


def compute_row(row: UnitkaRow, assumptions: UnitkaAssumptions) -> UnitkaRowComputed:
    x = row.purchase_price_vat_included  # X
    v = row.markup_multiplier  # V
    t = row.coinvest_percent  # T
    n = row.weight_kg or 0.0  # N
    ah = row.integration_fee  # AH
    ad = row.ozon_commission_percent  # AD

    # AX: =IF(N3<=3,60,70)+$AX$1*N3
    fulfillment_office_cost = (60.0 if n <= 3 else 70.0) + assumptions.fulfillment_office_rate_per_kg * n
    # AA: =AX3
    fulfillment_cost = fulfillment_office_cost

    volume_liters_computed = parse_volume_liters(row.dimensions_mm)
    # AW: =68+(AV3-0,113)*4,3+25
    ozon_volume_logistics_reference = (
        68 + (volume_liters_computed - 0.113) * 4.3 + 25 if volume_liters_computed is not None else None
    )
    # Z: =AW3 (с 2026-09-02; раньше было ручным числом). Если габариты (O) не задают
    # распознаваемый формат "ШxВxГ", AV/AW не считаются и в самом Excel формула Z
    # вернула бы #VALUE! — здесь берём 0.0, чтобы не ронять расчёт строки целиком.
    fbs_costs = ozon_volume_logistics_reference if ozon_volume_logistics_reference is not None else 0.0

    # S: =X3*(1+V3) — базовая цена, от неё считается всё остальное
    price = x * (1 + v)
    # R: =ROUND(S3/0.7,0)
    price_before_discount = round(price / 0.7)
    # U: =S3*T3
    ozon_points_discount = price * t
    # W: =S3-U3
    customer_price = price - ozon_points_discount
    # Y: =S3*Y$1
    sorting_delivery_cost = price * assumptions.sorting_delivery_rate
    # AB: =S3*$AB$1
    designer_salary_cost = price * assumptions.designer_salary_rate
    # AC: =S3*$AC$1
    fast_payout_cost = price * assumptions.fast_payout_rate
    # AE: =S3*AD3 (AD — INPUT, свой процент комиссии Ozon на строку, не допущение)
    ozon_commission_amount = price * ad
    # AF: =S3*$AF$1
    advertising_cost = price * assumptions.advertising_rate
    # AG: =S3*$AG$1
    acquiring_cost = price * assumptions.acquiring_rate
    # AI: =S3*$AI$1
    other_costs = price * assumptions.other_costs_rate
    # AJ: =S3*$AJ$1
    tax_amount = price * assumptions.tax_rate

    # AN: =SUM(X3,Y3,Z3,AA3,AB3,AC3,AG3,AH3,AI3,AJ3) — обратите внимание, AF (реклама)
    # и AE (комиссия Ozon) здесь НЕТ, они добавляются отдельно в AO/AP ниже.
    cost_basis = (
        x
        + sorting_delivery_cost
        + fbs_costs
        + fulfillment_cost
        + designer_salary_cost
        + fast_payout_cost
        + acquiring_cost
        + ah
        + other_costs
        + tax_amount
    )
    # AO: =AN3+AF3
    cost_basis_with_advertising = cost_basis + advertising_cost
    # AP: =AO3+AE3
    cost_basis_with_advertising_and_commission = cost_basis_with_advertising + ozon_commission_amount

    # AK: =S3-AP3
    net_profit = price - cost_basis_with_advertising_and_commission
    # AL: =AK3/AP3 (в оригинале НЕ /S3 — рентабельность считается от себестоимости, не от цены)
    profitability_percent = (
        net_profit / cost_basis_with_advertising_and_commission
        if cost_basis_with_advertising_and_commission
        else 0.0
    )

    # AM: =AQ3-W3 (только если есть цена сравнения AQ)
    idd_price_gap = (
        row.competitor_price_idd - customer_price if row.competitor_price_idd is not None else None
    )

    return UnitkaRowComputed(
        price_before_discount_vat_included=float(price_before_discount),
        price_with_discount_vat_included=round(price, 2),
        ozon_points_discount=round(ozon_points_discount, 2),
        customer_price=round(customer_price, 2),
        sorting_delivery_cost=round(sorting_delivery_cost, 2),
        fbs_costs=round(fbs_costs, 2),
        fulfillment_cost=round(fulfillment_cost, 2),
        designer_salary_cost=round(designer_salary_cost, 2),
        fast_payout_cost=round(fast_payout_cost, 2),
        ozon_commission_amount=round(ozon_commission_amount, 2),
        advertising_cost=round(advertising_cost, 2),
        acquiring_cost=round(acquiring_cost, 2),
        other_costs=round(other_costs, 2),
        tax_amount=round(tax_amount, 2),
        net_profit=round(net_profit, 2),
        profitability_percent=round(profitability_percent, 4),
        idd_price_gap=round(idd_price_gap, 2) if idd_price_gap is not None else None,
        cost_basis=round(cost_basis, 2),
        cost_basis_with_advertising=round(cost_basis_with_advertising, 2),
        cost_basis_with_advertising_and_commission=round(cost_basis_with_advertising_and_commission, 2),
        volume_liters_computed=volume_liters_computed,
        ozon_volume_logistics_reference=(
            round(ozon_volume_logistics_reference, 2)
            if ozon_volume_logistics_reference is not None
            else None
        ),
        fulfillment_office_cost=round(fulfillment_office_cost, 2),
    )
