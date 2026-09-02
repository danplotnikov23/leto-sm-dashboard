import re
from io import BytesIO

import pandas as pd

from app.domain.models import (
    CompetitorImportResult,
    CompetitorOffer,
    DataSource,
    ImportIssue,
    SupplierProduct,
)


class CompetitorImportService:
    """Imports Ozon competitor analytics exports and matches them to supplier products."""

    stop_words = {
        "без",
        "для",
        "или",
        "кор",
        "мм",
        "на",
        "под",
        "при",
        "с",
        "со",
        "шт",
    }

    def import_bytes(
        self,
        content: bytes,
        filename: str,
        products: list[SupplierProduct],
    ) -> tuple[CompetitorImportResult, dict[str, CompetitorOffer]]:
        frame = pd.read_excel(BytesIO(content))
        rows = self._parse_rows(frame)
        matches, issues = self.match_offers(rows, products)

        result = CompetitorImportResult(
            filename=filename,
            imported_rows=len(rows),
            matched_products=len(matches),
            skipped_rows=max(len(frame.index) - len(rows), 0),
            source=DataSource.EXCEL,
            issues=issues[:50],
        )
        return result, matches

    def match_offers(
        self,
        offers: list[CompetitorOffer],
        products: list[SupplierProduct],
    ) -> tuple[dict[str, CompetitorOffer], list[ImportIssue]]:
        matches: dict[str, CompetitorOffer] = {}
        issues: list[ImportIssue] = []

        for product in products:
            candidate, score = self._best_candidate(product, offers)
            if candidate is None:
                continue
            if score < 0.28:
                issues.append(
                    ImportIssue(
                        row_number=None,
                        field="match",
                        message=(
                            f"Слабое совпадение для {product.supplier_article}: "
                            f"{candidate.title}"
                        ),
                        severity="warning",
                    )
                )
                continue
            matches[product.id] = candidate

        return matches, issues

    def _parse_rows(self, frame: pd.DataFrame) -> list[CompetitorOffer]:
        columns = {self._normalize_key(column): column for column in frame.columns}
        title_column = self._pick_column(columns, ("название товара", "товар", "наименование"))
        lowest_price_column = self._pick_column(columns, ("самая низкая цена", "минимальная цена"))
        avg_price_column = self._pick_column(columns, ("средняя цена покупки", "средняя цена"))
        orders_column = self._pick_column(columns, ("заказано товаров", "количество заказов"))
        buyout_column = self._pick_column(columns, ("доля выкупа", "выкуп"))
        url_column = self._pick_column(columns, ("ссылка", "url", "карточка"))

        if title_column is None or (lowest_price_column is None and avg_price_column is None):
            return []

        offers: list[CompetitorOffer] = []
        for _, row in frame.iterrows():
            title = self._clean_title(row.get(title_column))
            price = self._money(row.get(lowest_price_column)) if lowest_price_column else None
            avg_purchase_price = (
                self._money(row.get(avg_price_column)) if avg_price_column else None
            )
            selected_price = price or avg_purchase_price
            if not title or selected_price is None:
                continue
            offers.append(
                CompetitorOffer(
                    title=title,
                    price_vat_included=selected_price,
                    url=self._url(row.get(url_column)) if url_column else None,
                    match_type="analog",
                    orders_count=self._int(row.get(orders_column)) if orders_column else None,
                    avg_purchase_price=avg_purchase_price,
                    buyout_rate=self._percent(row.get(buyout_column)) if buyout_column else None,
                    source=DataSource.EXCEL,
                )
            )
        return offers

    def _best_candidate(
        self,
        product: SupplierProduct,
        offers: list[CompetitorOffer],
    ) -> tuple[CompetitorOffer | None, float]:
        product_tokens = self._tokens(f"{product.title} {product.category or ''}")
        if not product_tokens:
            return None, 0.0

        scored: list[tuple[float, CompetitorOffer]] = []
        for offer in offers:
            offer_tokens = self._tokens(offer.title)
            if not offer_tokens:
                continue
            overlap = product_tokens & offer_tokens
            union = product_tokens | offer_tokens
            score = len(overlap) / len(union)
            score += self._dimension_score(product.title, offer.title)
            score += self._numeric_score(product.title, offer.title)
            score += self._mass_score(product.title, offer.title)
            product_group = self._group(product.title)
            offer_group = self._group(offer.title)
            if product_group and product_group == offer_group:
                score += 0.18
            if product.category and product.category.lower() in offer.title.lower():
                score += 0.08
            scored.append((score, offer))

        if not scored:
            return None, 0.0
        scored.sort(key=lambda item: (item[0], item[1].orders_count or 0), reverse=True)
        return scored[0][1], scored[0][0]

    def _tokens(self, value: str) -> set[str]:
        raw_tokens = re.findall(r"[а-яёa-z0-9]+", value.lower())
        return {
            token
            for token in raw_tokens
            if len(token) > 1
            and token not in self.stop_words
            and (not token.isdigit() or 1 <= int(token) <= 5000)
        }

    def _group(self, value: str) -> str | None:
        text = value.lower()
        groups = {
            "гвозди": ("гвозд",),
            "саморезы": ("саморез", "шуруп"),
            "дюбели": ("дюбел",),
            "крепеж": ("крепеж", "анкер", "болт", "гайк", "шайб"),
            "клей": ("клей", "герметик", "пена"),
            "смеси": ("цемент", "смесь", "штукатур", "шпатлев"),
            "электрика": ("кабель", "провод", "розетк", "выключател"),
        }
        for group, tokens in groups.items():
            if any(token in text for token in tokens):
                return group
        return None

    def _numeric_score(self, product_title: str, offer_title: str) -> float:
        product_numbers = self._number_tokens(product_title)
        offer_numbers = self._number_tokens(offer_title)
        if not product_numbers or not offer_numbers:
            return 0.0
        overlap = product_numbers & offer_numbers
        if overlap:
            return min(len(overlap) * 0.04, 0.12)
        if len(product_numbers) >= 2 and len(offer_numbers) >= 2:
            return -0.22
        return -0.08

    def _dimension_score(self, product_title: str, offer_title: str) -> float:
        product_dimensions = self._dimension_tokens(product_title)
        offer_dimensions = self._dimension_tokens(offer_title)
        if not product_dimensions or not offer_dimensions:
            return 0.0
        overlap = product_dimensions & offer_dimensions
        if product_dimensions == offer_dimensions:
            return 0.22
        if len(overlap) >= 2:
            return 0.08
        if len(overlap) == 1:
            return -0.18
        return -0.28

    def _mass_score(self, product_title: str, offer_title: str) -> float:
        product_mass = self._mass_grams(product_title)
        offer_mass = self._mass_grams(offer_title)
        if product_mass is None or offer_mass is None:
            return 0.0
        ratio = max(product_mass, offer_mass) / max(min(product_mass, offer_mass), 1)
        if ratio <= 1.8:
            return 0.08
        if ratio >= 3:
            return -0.3
        return -0.12

    def _number_tokens(self, value: str) -> set[str]:
        text = value.lower().replace(",", ".").replace("х", "x")
        return {
            token.rstrip(".0") if token.endswith(".0") else token
            for token in re.findall(r"\d+(?:\.\d+)?", text)
            if 1 <= float(token) <= 5000
        }

    def _dimension_tokens(self, value: str) -> set[str]:
        text = value.lower().replace(",", ".").replace("х", "x")
        tokens: set[str] = set()
        for match in re.finditer(r"(\d+(?:\.\d+)?)(?:\s*x\s*)(\d+(?:\.\d+)?)", text):
            tokens.add(self._normalize_number_token(match.group(1)))
            tokens.add(self._normalize_number_token(match.group(2)))
        return tokens

    def _normalize_number_token(self, value: str) -> str:
        return value.rstrip(".0") if value.endswith(".0") else value

    def _mass_grams(self, value: str) -> float | None:
        text = value.lower().replace(",", ".").replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?)(кг|kg|гр|г|g)(?![а-яa-z])", text)
        if not match:
            return None
        amount = float(match.group(1))
        unit = match.group(2)
        return amount * 1000 if unit in {"кг", "kg"} else amount

    def _pick_column(self, columns: dict[str, object], names: tuple[str, ...]) -> object | None:
        for key, original in columns.items():
            if any(name in key for name in names):
                return original
        return None

    def _normalize_key(self, value: object) -> str:
        return re.sub(r"\s+", " ", str(value).strip().lower())

    def _clean_title(self, value: object) -> str:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            return ""
        return re.sub(r"\s+", " ", text)

    def _money(self, value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace("\xa0", " ").replace(",", ".")
        match = re.search(r"-?\d+(?:\s\d{3})*(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0).replace(" ", ""))

    def _int(self, value: object) -> int | None:
        parsed = self._money(value)
        return int(parsed) if parsed is not None else None

    def _percent(self, value: object) -> float | None:
        parsed = self._money(value)
        if parsed is None:
            return None
        return parsed / 100 if parsed > 1 else parsed

    def _url(self, value: object) -> str | None:
        text = str(value or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
        return None
