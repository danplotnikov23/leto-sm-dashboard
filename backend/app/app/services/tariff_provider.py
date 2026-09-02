import gzip
import re
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from app.domain.models import DataSource, SupplierProduct, TariffRule


class CommissionRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str
    product_type: str
    fbs_up_to_100: float
    fbs_100_to_300: float
    fbs_over_300: float


class CommissionDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    source_file: str
    rows: tuple[CommissionRow, ...]


class TariffProvider:
    """Official FBS commission bands plus explicitly estimated logistics."""

    version = "ozon-fbs-commissions-2026-06-01"
    _dataset_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "ozon_fbs_commissions_2026_06_01.json.gz"
    )
    _category_aliases = {
        "гвозди": "гвозди",
        "саморезы": "саморезы",
        "трапы": "трап для душа",
        "смесители": "смеситель",
        "раковины": "раковина",
        "герметики": "герметик",
        "краски": "краска",
        "валики": "валик малярный",
        "лопаты": "лопата",
        "светильники": "настенно потолочный светильник",
    }
    _calculator_over_300_overrides = {
        # calculator.ozon.ru export, 17.06.2026, product type "Сифон сливной".
        "сифон сливной": 46.0,
    }

    def __init__(self) -> None:
        with gzip.open(self._dataset_path, "rb") as source:
            self._dataset = TypeAdapter(CommissionDataset).validate_json(source.read())
        self._by_type = {
            self._normalize(row.product_type): row for row in self._dataset.rows
        }
        types_by_first_token: dict[str, list[tuple[str, CommissionRow]]] = defaultdict(list)
        for normalized_type, row in self._by_type.items():
            if len(normalized_type) < 7:
                continue
            first_token = normalized_type.split(maxsplit=1)[0]
            types_by_first_token[first_token].append((normalized_type, row))
        self._types_by_first_token = dict(types_by_first_token)
        by_category: dict[str, list[CommissionRow]] = defaultdict(list)
        for row in self._dataset.rows:
            by_category[self._normalize(row.category)].append(row)
        self._by_category = dict(by_category)

    def get_rule(
        self,
        product: SupplierProduct,
        sale_price_vat_included: float | None = None,
    ) -> TariffRule:
        price = sale_price_vat_included or product.purchase_price_vat_included
        matched = self._match_commission_row(product)
        if matched is not None:
            commission = self._commission_for_price(matched, price)
            label = f"Ozon FBS от 01.06.2026: {matched.product_type}"
            calculator_override = self._calculator_commission_override(matched, price)
            if calculator_override is not None:
                commission = calculator_override
                label = f"Калькулятор Ozon от 17.06.2026: {matched.product_type}"
            warning = (
                "Комиссия взята из официальной таблицы Ozon. База FBS до 1 л "
                "сверена с калькулятором Ozon 17.06.2026; для других габаритов "
                "логистика остается оценочной."
            )
            source = DataSource.EXCEL
            matched_category = matched.category
            matched_type = matched.product_type
        else:
            commission = self._fallback_commission(price)
            label = "Консервативная оценка по ценовому диапазону FBS"
            warning = (
                "Тип товара не сопоставлен с официальной таблицей Ozon. "
                "Комиссия оценочная; база FBS до 1 л сверена с калькулятором "
                "Ozon 17.06.2026, другие габариты требуют проверки."
            )
            source = DataSource.ESTIMATE
            matched_category = None
            matched_type = None

        return TariffRule(
            version=self.version,
            category=product.category or "unknown",
            commission_percent=commission,
            # Official Ozon calculator export, 17.06.2026: FBS order processing
            # 30 RUB + logistics 17 RUB + delivery to pickup point 16 RUB for
            # a 0.144 l / 0.02 kg item.
            fbs_logistics_base=63.0,
            fbo_logistics_base=105.0,
            acquiring_percent=1.0,
            storage_per_liter_month=0.0,
            source=source,
            matched_ozon_category=matched_category,
            matched_ozon_product_type=matched_type,
            commission_source_label=label,
            warning=warning,
        )

    def _match_commission_row(self, product: SupplierProduct) -> CommissionRow | None:
        category = self._normalize(product.category or "")
        title = self._normalize(product.title)

        alias = self._category_aliases.get(category)
        if alias is not None and alias in self._by_type:
            return self._by_type[alias]
        if category in self._by_type:
            return self._by_type[category]

        candidates: dict[str, CommissionRow] = {}
        for token in set(title.split()):
            candidates.update(self._types_by_first_token.get(token, ()))
        title_matches = [
            row for normalized_type, row in candidates.items() if normalized_type in title
        ]
        if title_matches:
            return max(title_matches, key=lambda row: len(self._normalize(row.product_type)))

        category_rows = self._by_category.get(category, [])
        if category_rows and self._all_rates_equal(category_rows):
            return category_rows[0]
        return None

    @staticmethod
    def _commission_for_price(row: CommissionRow, price: float) -> float:
        if price <= 100:
            return row.fbs_up_to_100
        if price <= 300:
            return row.fbs_100_to_300
        return row.fbs_over_300

    def _calculator_commission_override(
        self,
        row: CommissionRow,
        price: float,
    ) -> float | None:
        if price <= 300:
            return None
        return self._calculator_over_300_overrides.get(
            self._normalize(row.product_type)
        )

    @staticmethod
    def _fallback_commission(price: float) -> float:
        if price <= 100:
            return 14.0
        if price <= 300:
            return 20.0
        return 50.0

    @staticmethod
    def _all_rates_equal(rows: list[CommissionRow]) -> bool:
        rates = {
            (row.fbs_up_to_100, row.fbs_100_to_300, row.fbs_over_300)
            for row in rows
        }
        return len(rates) == 1

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.sub(r"[^a-zа-я0-9]+", " ", value.casefold().replace("ё", "е")).split())
