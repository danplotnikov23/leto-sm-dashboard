"""Доменная модель «живой» Юнитки Лето СМ.

Один-в-один цифровая копия листа `15.06.26` файла
`Downloads/Юнитка Лето СМ.xlsx` (source of truth, см. проектную память
`project_unitka_source_of_truth`). Колонки называются по-английски, но
каждое поле подписано исходной буквой столбца Excel и русским заголовком —
это НЕ отдельная бизнес-логика, а прямой перенос существующей таблицы,
чтобы её можно было редактировать и пересчитывать прямо на сайте.

INPUT-поля — то, что вводится руками (или подтягивается из Ozon API).
Всё остальное (see `unitka_engine.py`) — производные величины, которые
были формулами в Excel и остаются формулами здесь: считаются функцией от
INPUT-полей, никогда не хранятся как отдельно введённое число.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UnitkaAssumptions(BaseModel):
    """Ячейки-допущения строки 1 листа `15.06.26` (абсолютные ссылки $X$1).

    Это глобальные для всей юнитки проценты/коэффициенты, а не данные
    конкретного товара — в Excel они лежали в отдельной строке и на них
    ссылались формулы вида `=S3*$AB$1`. Здесь это ровно то же самое: одна
    точка правды на всю таблицу, а не константа, размазанная по коду.
    """

    model_config = ConfigDict(extra="forbid")

    # Y$1 — ставка для Y ("Отвоз на сортировку озона")
    sorting_delivery_rate: float = 0.02
    # $AB$1 — ставка для AB ("Зарплата дизайнер, руб.")
    designer_salary_rate: float = 0.02
    # $AC$1 — ставка для AC ("Быстрый вывод с озон")
    fast_payout_rate: float = 0.0245
    # $AF$1 — ставка для AF ("Затраты на рекламу и продвижение")
    advertising_rate: float = 0.05
    # $AG$1 — ставка для AG ("Эквайринг")
    acquiring_rate: float = 0.011
    # $AI$1 — ставка для AI ("Прочие расходы")
    other_costs_rate: float = 0.015
    # $AJ$1 — ставка для AJ ("Налог 1% у нас льгота")
    tax_rate: float = 0.01
    # $AX$1 — руб/кг в формуле AX ("Фулфилмент-контора")
    fulfillment_office_rate_per_kg: float = 1.7
    # AL$1 в файле заполнена (0.05), но ни одна формула строки 3 на неё не
    # ссылается — похоже на неиспользуемый черновик целевой рентабельности.
    # Оставлено как есть, поле сюда намеренно не включено (см. допущение
    # выше — не выдумываем формулу, которой нет).


class UnitkaRow(BaseModel):
    """Один SKU листа `15.06.26` — все 50 содержательных колонок (A..AX).

    Последние 6 колонок исходника (AY..BD) в файле пустые, без заголовков
    и без данных — не переносим их сюда, пока в источнике не появится
    реальное содержимое (не гадаем, что там должно быть).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Внутренний id строки (не из Excel)")

    # --- A..Q: карточка товара (INPUT) ---
    row_number: int | None = None  # A "Номер"
    supplier_article: str  # B "Артикл прайс"
    fulfillment_scheme: str | None = None  # C "Схема реализации" (FBS/FBO/realFBS)
    ozon_listing: str | None = None  # D "Выкладка OZON"
    stock: float | None = None  # E "Остатки"
    ozon_sku_id: str | None = None  # F "Ozon SKU ID"
    title: str  # G "Название"
    product_type: str | None = None  # H "Тип" (напр. "Центр СМ")
    status: str | None = None  # I "Статус"
    ozon_visibility: str | None = None  # J "Видимость на OZON"
    in_stock_ozon: float | None = None  # K "На складе Ozon"
    in_stock_own: float | None = None  # L "На моих складах"
    volume_liters_manual: float | None = None  # M "Объем, л" (ручной, не путать с AV)
    weight_kg: float | None = None  # N "вес, кг"
    dimensions_mm: str | None = None  # O "Размеры в мм (ШxВxГ)", напр. "1050×440×1050"
    tn_ved: str | None = None  # P "ТН ВЭД"
    honest_mark_required: str | None = None  # Q "Нужен ли честный знак"

    # --- INPUT-параметры расчёта ---
    coinvest_percent: float = 0.0  # T "Процент соинвест"
    markup_multiplier: float = 0.0  # V "Торговая наценка" — множитель, не рубли (см. формулу S)
    purchase_price_vat_included: float  # X "Закупочная цена с НДС, руб."
    fbs_costs: float = 0.0  # Z "FBS затраты" (часто = скопированное значение AW на момент ввода)
    ozon_commission_percent: float = 0.0  # AD "Вознаграждение OZON, %"
    integration_fee: float = 0.0  # AH "Сбор за интеграцию, руб."

    # --- AQ..AU: справочные цены/ссылки конкурентов (INPUT) ---
    competitor_price_idd: float | None = None  # AQ "Цена на сайте идеи для дома"
    competitor_price_ozon: float | None = None  # AR "Цена конкурент на озон"
    url_idd: str | None = None  # AS "Идеи для дома"
    url_tdcsm: str | None = None  # AT "Центр СМ"
    url_competitor: str | None = None  # AU "Конкурент"


class UnitkaRowComputed(BaseModel):
    """Производные (формульные) колонки — результат `UnitkaEngine.compute()`.

    Каждое поле = один столбец Excel; в `unitka_engine.py` у каждого поля
    есть комментарий с точной исходной формулой для сверки.
    """

    model_config = ConfigDict(extra="forbid")

    price_before_discount_vat_included: float  # R
    price_with_discount_vat_included: float  # S — базовая цена, от неё считается всё остальное
    ozon_points_discount: float  # U
    customer_price: float  # W
    sorting_delivery_cost: float  # Y
    fulfillment_cost: float  # AA (=AX)
    designer_salary_cost: float  # AB
    fast_payout_cost: float  # AC
    ozon_commission_amount: float  # AE
    advertising_cost: float  # AF
    acquiring_cost: float  # AG
    other_costs: float  # AI
    tax_amount: float  # AJ
    net_profit: float  # AK
    profitability_percent: float  # AL
    idd_price_gap: float | None  # AM (None, если нет AQ)
    cost_basis: float  # AN
    cost_basis_with_advertising: float  # AO
    cost_basis_with_advertising_and_commission: float  # AP
    volume_liters_computed: float | None  # AV (None, если O не парсится)
    ozon_volume_logistics_reference: float | None  # AW — справочно, в P&L не участвует
    fulfillment_office_cost: float  # AX


class UnitkaItem(BaseModel):
    """Строка + её расчёт — то, что отдаёт API."""

    model_config = ConfigDict(extra="forbid")

    row: UnitkaRow
    computed: UnitkaRowComputed
