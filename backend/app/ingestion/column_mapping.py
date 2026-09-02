from dataclasses import dataclass
from re import sub


@dataclass(frozen=True)
class ColumnRule:
    target: str
    aliases: tuple[str, ...]


RULES: tuple[ColumnRule, ...] = (
    ColumnRule("supplier_article", ("артикул", "артикул поставщика", "код", "sku")),
    ColumnRule(
        "title",
        ("название", "наименование", "номенклатура", "продукт", "товар", "имя товара"),
    ),
    ColumnRule("category", ("категория", "группа", "раздел")),
    ColumnRule(
        "purchase_price_vat_included",
        (
            "цена",
            "закупка",
            "закупочная цена",
            "прайс",
            "для оптовиков",
            "опт",
        ),
    ),
    ColumnRule(
        "package",
        ("упаковка", "тип упаковки", "фасовка", "объем тары", "объём тары", "тара"),
    ),
    ColumnRule("weight_kg", ("вес", "вес кг", "масса", "weight")),
    ColumnRule("length_cm", ("длина", "длина см", "length")),
    ColumnRule("width_cm", ("ширина", "ширина см", "width")),
    ColumnRule("height_cm", ("высота", "высота см", "height")),
    ColumnRule(
        "multiplicity",
        (
            "кратность",
            "кратность отгрузки",
            "кол во в уп",
            "количество в упаковке",
        ),
    ),
    ColumnRule(
        "stock",
        (
            "свободный остаток",
            "доступный остаток",
            "остаток на складе",
            "остаток",
            "остатки",
            "в наличии",
            "наличие",
            "доступно",
            "свободно",
            "количество на складе",
            "кол во на складе",
            "складской остаток",
            "stock",
            "available stock",
        ),
    ),
    ColumnRule("brand", ("бренд", "марка", "производитель")),
    ColumnRule("barcode", ("штрихкод", "ean", "barcode", "баркод")),
)


REQUIRED_COLUMNS = {"supplier_article", "title", "purchase_price_vat_included"}
TRACKED_FIELDS: tuple[str, ...] = (
    "supplier_article",
    "title",
    "category",
    "purchase_price_vat_included",
    "package",
    "weight_kg",
    "length_cm",
    "width_cm",
    "height_cm",
    "multiplicity",
    "stock",
    "brand",
    "barcode",
)
FIELD_LABELS: dict[str, str] = {
    "supplier_article": "Артикул",
    "title": "Название",
    "category": "Категория",
    "purchase_price_vat_included": "Закупка",
    "package": "Упаковка",
    "weight_kg": "Вес",
    "length_cm": "Длина",
    "width_cm": "Ширина",
    "height_cm": "Высота",
    "multiplicity": "Кратность",
    "stock": "Остаток",
    "brand": "Бренд",
    "barcode": "Штрихкод",
}


def normalize_header(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = sub(r"[\n\r\t]+", " ", text)
    text = sub(r"[^a-zа-я0-9]+", " ", text)
    return sub(r"\s+", " ", text).strip()


def detect_columns(headers: list[object]) -> dict[str, str]:
    normalized_to_original = {normalize_header(header): str(header) for header in headers}
    mapping: dict[str, str] = {}

    for rule in RULES:
        for alias in rule.aliases:
            normalized_alias = normalize_header(alias)
            exact = normalized_to_original.get(normalized_alias)
            if exact:
                mapping[rule.target] = exact
                break
            contains = next(
                (
                    original
                    for normalized, original in normalized_to_original.items()
                    if normalized_alias in normalized
                ),
                None,
            )
            if contains:
                mapping[rule.target] = contains
                break

    return mapping


def detect_stock_columns(headers: list[object]) -> list[str]:
    candidates: list[tuple[int, int, str, str]] = []
    exact_names = {
        "остаток",
        "остатки",
        "наличие",
        "в наличии",
        "доступно",
        "свободно",
        "свободный остаток",
        "доступный остаток",
        "stock",
        "available stock",
    }
    excluded_tokens = (
        "минималь",
        "максималь",
        "упаков",
        "кратност",
        "резерв",
        "заказ",
        "продан",
        "ожида",
        "в пути",
    )
    for position, header in enumerate(headers):
        normalized = normalize_header(header)
        if not normalized or any(token in normalized for token in excluded_tokens):
            continue
        is_stock = (
            normalized in exact_names
            or "остат" in normalized
            or "налич" in normalized
            or "доступ" in normalized
            or normalized == "stock"
            or ("колич" in normalized and "склад" in normalized)
            or ("кол во" in normalized and "склад" in normalized)
        )
        if not is_stock:
            continue
        is_aggregate = normalized in exact_names or any(
            token in normalized for token in ("итого", "общий", "всего")
        )
        score = 100 if is_aggregate else 50
        if "свобод" in normalized or "доступ" in normalized:
            score += 20
        candidates.append((score, position, str(header), normalized))

    if not candidates:
        return []
    aggregate = [candidate for candidate in candidates if candidate[0] >= 100]
    if aggregate:
        best = max(aggregate, key=lambda candidate: (candidate[0], -candidate[1]))
        return [best[2]]
    return [candidate[2] for candidate in sorted(candidates, key=lambda item: item[1])]
