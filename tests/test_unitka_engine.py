"""Проверка движка юнитки на реальных строках `Юнитка Лето СМ.xlsx` (2026-09-02).

Ожидаемые числа посчитаны вручную (пошагово, без использования этого же движка —
независимая сверка) при первом разборе формул листа `15.06.26`. Перекрёстный признак
корректности: рентабельность SKU №1 выходит ровно 5.00% — совпадает с реальным именем
бэкапа `..._before_S_5pct_margin.xlsx`, т.е. цена S была тогда осознанно подобрана под
целевую маржу 5%.

Z (FBS затраты) с 2026-09-02 в файле — формула `=AW3` (раньше было ручным числом
2178.4, введённым как разовая копия AW; теперь связь стала живой формулой) —
`net_profit` ниже пересчитан под текущую версию файла, а не под старое ручное число.
"""

from app.domain.unitka import UnitkaAssumptions, UnitkaRow
from app.services.unitka_engine import compute_row, parse_volume_liters

ASSUMPTIONS = UnitkaAssumptions()  # значения по умолчанию = ячейки допущений из файла


def test_row3_chasha_kostrovaya_matches_manual_calculation() -> None:
    row = UnitkaRow(
        id="test-1",
        supplier_article="10865981",
        title="Чаша костровая большая 1050×440",
        weight_kg=72,
        dimensions_mm="1050×440×1050",
        coinvest_percent=0.4,
        markup_multiplier=3.0482,
        purchase_price_vat_included=10766,
        ozon_commission_percent=0.5,
        integration_fee=20,
    )
    result = compute_row(row, ASSUMPTIONS)

    # S3 = X3*(1+V3) = 10766*4.0482
    assert result.price_with_discount_vat_included == 43582.92
    # AK3 = S3 - AP3 (пересчитано под Z=AW живой формулой, см. докстринг модуля)
    assert result.net_profit == 2075.39
    # AL3 = AK3/AP3 — ровно 5.00%, подтверждено именем бэкапа "..._before_S_5pct_margin.xlsx"
    assert result.profitability_percent == 0.05
    # Z (fbs_costs) теперь ровно равен AW — это формула =AW3, не независимый ввод
    assert result.fbs_costs == result.ozon_volume_logistics_reference


def test_row4_mangal_razbornoy() -> None:
    row = UnitkaRow(
        id="test-2",
        supplier_article="10827676",
        title="Мангал разборный Л-03",
        weight_kg=5,
        dimensions_mm="≈400×80×600",
        coinvest_percent=0.4,
        markup_multiplier=2.4611,
        purchase_price_vat_included=6102,
        ozon_commission_percent=0.5,
        integration_fee=20,
    )
    result = compute_row(row, ASSUMPTIONS)
    # S4 = 6102*(1+2.4611) = 6102*3.4611
    assert result.price_with_discount_vat_included == round(6102 * 3.4611, 2)
    assert result.net_profit > 0


def test_parse_volume_liters_handles_approx_prefix() -> None:
    # "≈" перед первым числом — как в реальных данных (например, ряд с Мангалом)
    assert parse_volume_liters("≈400×80×600") == 400 * 80 * 600 / 1_000_000


def test_parse_volume_liters_returns_none_for_missing_dimensions() -> None:
    assert parse_volume_liters(None) is None
    assert parse_volume_liters("") is None
    assert parse_volume_liters("мусор") is None


def test_idd_price_gap_is_none_without_competitor_price() -> None:
    row = UnitkaRow(
        id="test-3",
        supplier_article="X",
        title="Товар без сравнения",
        purchase_price_vat_included=1000,
        markup_multiplier=1.0,
        ozon_commission_percent=0.3,
    )
    result = compute_row(row, ASSUMPTIONS)
    assert result.idd_price_gap is None
