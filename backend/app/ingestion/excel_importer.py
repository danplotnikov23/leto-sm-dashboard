from io import BytesIO
from pathlib import Path
from re import search
from uuid import uuid4

import pandas as pd

from app.domain.models import (
    Dimensions,
    ImportFieldCoverage,
    ImportIssue,
    PriceImportVersion,
    SupplierProduct,
)
from app.ingestion.column_mapping import (
    FIELD_LABELS,
    REQUIRED_COLUMNS,
    TRACKED_FIELDS,
    detect_columns,
    detect_stock_columns,
)


class ExcelImportService:
    def import_bytes(
        self,
        content: bytes,
        filename: str,
        supplier_name: str | None = None,
    ) -> PriceImportVersion:
        resolved_supplier = self.infer_supplier_name(filename, supplier_name)
        sheets = pd.read_excel(
            BytesIO(content),
            engine=self._excel_engine(content, filename),
            header=None,
            sheet_name=None,
        )
        versions = [
            (sheet_name, self.import_frame(frame, filename, resolved_supplier))
            for sheet_name, frame in sheets.items()
        ]
        if len(versions) == 1:
            return versions[0][1]
        return self._merge_sheet_versions(filename, versions, resolved_supplier)

    def import_frame(
        self,
        frame: pd.DataFrame,
        filename: str,
        supplier_name: str | None = None,
    ) -> PriceImportVersion:
        resolved_supplier = self.infer_supplier_name(filename, supplier_name)
        frame = self._promote_header(frame)
        frame = frame.dropna(how="all")
        mapping = detect_columns(list(frame.columns))
        stock_columns = detect_stock_columns(list(frame.columns))
        if stock_columns:
            mapping["stock"] = stock_columns[0]
        coverage = self._field_coverage(frame, mapping, stock_columns)
        issues: list[ImportIssue] = []
        missing = REQUIRED_COLUMNS - set(mapping)
        for column in sorted(missing):
            issues.append(
                ImportIssue(
                    row_number=None,
                    field=column,
                    message=f"Не найдена обязательная колонка: {column}",
                    severity="error",
                )
            )
        if missing:
            return PriceImportVersion(
                filename=filename,
                supplier_name=resolved_supplier,
                total_rows=len(frame.index),
                accepted_rows=0,
                source_columns=[str(column) for column in frame.columns],
                detected_columns=mapping,
                field_coverage=coverage,
                products=[],
                issues=issues,
            )

        products: list[SupplierProduct] = []
        seen_articles: set[str] = set()
        seen_barcodes: set[str] = set()
        current_category: str | None = None
        current_title: str | None = None
        section_rows = 0
        for index, row in frame.iterrows():
            row_number = int(index)
            section = self._section_title(row, mapping)
            if section is not None:
                current_category = section
                section_rows += 1
                continue
            row_title = self._text(row.get(mapping["title"]))
            if row_title:
                current_title = row_title
            product = self._parse_row(
                row,
                mapping,
                stock_columns,
                row_number,
                issues,
                fallback_title=current_title,
            )
            if product is None:
                continue
            if not product.category and current_category:
                product.category = current_category
            self._add_quality_warnings(product, row_number, issues)
            article_key = product.supplier_article.lower()
            barcode_key = product.barcode.strip() if product.barcode else None
            if article_key in seen_articles or (
                barcode_key is not None and barcode_key in seen_barcodes
            ):
                issues.append(
                    ImportIssue(
                        row_number=row_number,
                        field="supplier_article",
                        message="Дубль товара пропущен.",
                        severity="warning",
                    )
                )
                continue
            seen_articles.add(article_key)
            if barcode_key is not None:
                seen_barcodes.add(barcode_key)
            products.append(product)

        return PriceImportVersion(
            id=str(uuid4()),
            filename=filename,
            supplier_name=resolved_supplier,
            total_rows=len(frame.index),
            accepted_rows=len(products),
            section_rows=section_rows,
            source_columns=[str(column) for column in frame.columns],
            detected_columns=mapping,
            field_coverage=self._with_product_coverage(coverage, products),
            products=[
                product.model_copy(update={"supplier_name": resolved_supplier})
                for product in products
            ],
            issues=issues,
        )

    @staticmethod
    def infer_supplier_name(filename: str, supplier_name: str | None = None) -> str:
        explicit = (supplier_name or "").strip()
        if explicit:
            return explicit
        stem = Path(filename).stem.strip()
        normalized = stem.casefold().replace("_", " ")
        known = (
            (("pro-brite", "pro brite"), "Pro-Brite"),
            (("центр см", "price export"), "Центр СМ"),
            (("крепеж", "крепёж"), "ООО КРЕПЕЖ"),
            (("м8", "m8"), "М8"),
        )
        for markers, label in known:
            if any(marker in normalized for marker in markers):
                return label
        return "Не указан"

    def _parse_row(
        self,
        row: pd.Series,
        mapping: dict[str, str],
        stock_columns: list[str],
        row_number: int,
        issues: list[ImportIssue],
        fallback_title: str | None = None,
    ) -> SupplierProduct | None:
        supplier_article = self._text(row.get(mapping["supplier_article"]))
        title = self._text(row.get(mapping["title"])) or fallback_title or ""
        purchase_price = self._number(row.get(mapping["purchase_price_vat_included"]))

        if not supplier_article or not title or purchase_price is None:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="required",
                    message="Строка пропущена: нет артикула, названия или закупочной цены.",
                    severity="error",
                )
            )
            return None
        if purchase_price < 0:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="purchase_price_vat_included",
                    message="Отрицательная закупочная цена недопустима.",
                    severity="error",
                )
            )
            return None

        product = SupplierProduct(
            supplier_article=supplier_article,
            title=title,
            category=self._optional_text(row, mapping, "category"),
            purchase_price_vat_included=purchase_price,
            package=self._optional_text(row, mapping, "package"),
            weight_kg=self._number(row.get(mapping.get("weight_kg", ""))),
            dimensions=Dimensions(
                length_cm=self._number(row.get(mapping.get("length_cm", ""))),
                width_cm=self._number(row.get(mapping.get("width_cm", ""))),
                height_cm=self._number(row.get(mapping.get("height_cm", ""))),
            ),
            multiplicity=self._number(row.get(mapping.get("multipity", "")))
            or self._number(row.get(mapping.get("multiplicity", ""))),
            stock=self._stock_value(row, stock_columns),
            brand=self._optional_text(row, mapping, "brand"),
            barcode=self._optional_text(row, mapping, "barcode"),
        )
        return product

    def _merge_sheet_versions(
        self,
        filename: str,
        versions: list[tuple[str, PriceImportVersion]],
        supplier_name: str,
    ) -> PriceImportVersion:
        products: list[SupplierProduct] = []
        seen_articles: set[str] = set()
        issues: list[ImportIssue] = []
        detected: dict[str, str] = {}
        source_columns: list[str] = []
        coverage_by_field: dict[str, list[ImportFieldCoverage]] = {
            field: [] for field in TRACKED_FIELDS
        }
        for sheet_name, version in versions:
            for product in version.products:
                key = product.supplier_article.casefold()
                if key in seen_articles:
                    issues.append(
                        ImportIssue(
                            row_number=None,
                            field="supplier_article",
                            message=f"[лист {sheet_name}] Дубль артикула между листами пропущен.",
                            severity="warning",
                        )
                    )
                    continue
                seen_articles.add(key)
                products.append(product)
            issues.extend(
                issue.model_copy(update={"message": f"[лист {sheet_name}] {issue.message}"})
                for issue in version.issues
            )
            source_columns.extend(f"{sheet_name}: {column}" for column in version.source_columns)
            for field, column in version.detected_columns.items():
                detected.setdefault(field, f"{sheet_name}: {column}")
            for field in version.field_coverage:
                coverage_by_field[field.field].append(field)

        field_coverage: list[ImportFieldCoverage] = []
        total_rows = sum(version.total_rows for _, version in versions)
        for field in TRACKED_FIELDS:
            entries = coverage_by_field[field]
            present_rows = sum(entry.present_rows for entry in entries)
            source_names = list(
                dict.fromkeys(
                    entry.source_column for entry in entries if entry.source_column is not None
                )
            )
            field_coverage.append(
                ImportFieldCoverage(
                    field=field,
                    label=FIELD_LABELS.get(field, field),
                    source_column="; ".join(source_names) or None,
                    present_rows=present_rows,
                    missing_rows=max(total_rows - present_rows, 0),
                    coverage_percent=(
                        round(present_rows / total_rows * 100, 2) if total_rows else 0.0
                    ),
                )
            )

        return PriceImportVersion(
            filename=filename,
            supplier_name=supplier_name,
            total_rows=total_rows,
            accepted_rows=len(products),
            section_rows=sum(version.section_rows for _, version in versions),
            source_columns=source_columns,
            detected_columns=detected,
            field_coverage=field_coverage,
            products=products,
            issues=issues,
        )

    def _promote_header(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self._has_required_columns(frame):
            result = frame.copy()
            result.index = range(2, len(result.index) + 2)
            return result

        header_index = self._detect_header_row(frame)
        if header_index is None:
            result = frame.copy()
            result.columns = [str(column) for column in result.columns]
            result.index = range(2, len(result.index) + 2)
            return result

        headers = [
            self._text(value) or f"column_{position + 1}"
            for position, value in enumerate(frame.iloc[header_index])
        ]
        result = frame.iloc[header_index + 1 :].copy()
        result.columns = headers
        result = result.dropna(how="all")
        result.index = range(header_index + 2, header_index + 2 + len(result.index))
        return result

    def _has_required_columns(self, frame: pd.DataFrame) -> bool:
        mapping = detect_columns(list(frame.columns))
        return set(mapping) >= REQUIRED_COLUMNS

    def _detect_header_row(self, frame: pd.DataFrame) -> int | None:
        best_index: int | None = None
        best_score = 0
        scan_limit = min(len(frame.index), 40)
        for position in range(scan_limit):
            headers = [self._text(value) for value in frame.iloc[position].tolist()]
            mapping = detect_columns(headers)
            required_count = len(REQUIRED_COLUMNS & set(mapping))
            score = required_count * 20 + len(mapping)
            if required_count == len(REQUIRED_COLUMNS) and score > best_score:
                best_index = position
                best_score = score
        return best_index

    def _section_title(self, row: pd.Series, mapping: dict[str, str]) -> str | None:
        supplier_article = self._text(row.get(mapping["supplier_article"]))
        title = self._text(row.get(mapping["title"]))
        purchase_price = self._number(row.get(mapping["purchase_price_vat_included"]))
        non_empty_values = [self._text(value) for value in row.tolist()]
        non_empty_count = sum(1 for value in non_empty_values if value)
        first_value = non_empty_values[0] if non_empty_values else ""
        sole_value = next((value for value in non_empty_values if value), "")
        if title and non_empty_count == 1 and not supplier_article and purchase_price is None:
            return title
        if sole_value and non_empty_count == 1 and not supplier_article and purchase_price is None:
            return sole_value
        if first_value and non_empty_count == 1 and not title and not purchase_price:
            return first_value
        if (
            first_value
            and non_empty_count <= 2
            and not supplier_article
            and not title
            and purchase_price is None
        ):
            return first_value
        return None

    def _add_quality_warnings(
        self,
        product: SupplierProduct,
        row_number: int,
        issues: list[ImportIssue],
    ) -> None:
        if not product.category:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="category",
                    message="Не указана категория: расчет комиссии Ozon будет оценочным.",
                    severity="warning",
                )
            )
        if product.weight_kg is None:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="weight_kg",
                    message="Не указан вес: логистика будет оценочной.",
                    severity="warning",
                )
            )
        if product.dimensions.volume_liters is None:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="dimensions",
                    message="Не указаны полные габариты: логистика будет оценочной.",
                    severity="warning",
                )
            )
        if product.stock is None:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="stock",
                    message="Не указан остаток: товар попадет в каталог без складской доступности.",
                    severity="warning",
                )
            )
        elif product.stock <= 0:
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    field="stock",
                    message="Остаток равен нулю: товар недоступен для запуска.",
                    severity="warning",
                )
            )

    def _field_coverage(
        self,
        frame: pd.DataFrame,
        mapping: dict[str, str],
        stock_columns: list[str] | None = None,
    ) -> list[ImportFieldCoverage]:
        total_rows = len(frame.index)
        result: list[ImportFieldCoverage] = []
        for field in TRACKED_FIELDS:
            source_column = mapping.get(field)
            present_rows = 0
            if field == "stock" and stock_columns:
                source_column = " + ".join(stock_columns)
                present_rows = int(
                    frame[stock_columns]
                    .apply(
                        lambda row: any(self._has_value(value) for value in row),
                        axis=1,
                    )
                    .sum()
                )
            elif source_column is not None and source_column in frame.columns:
                present_rows = int(frame[source_column].apply(self._has_value).sum())
            missing_rows = max(total_rows - present_rows, 0)
            coverage_percent = round((present_rows / total_rows * 100), 2) if total_rows else 0.0
            result.append(
                ImportFieldCoverage(
                    field=field,
                    label=FIELD_LABELS.get(field, field),
                    source_column=source_column,
                    present_rows=present_rows,
                    missing_rows=missing_rows,
                    coverage_percent=coverage_percent,
                )
            )
        return result

    def _with_product_coverage(
        self,
        coverage: list[ImportFieldCoverage],
        products: list[SupplierProduct],
    ) -> list[ImportFieldCoverage]:
        if not products:
            return coverage
        result: list[ImportFieldCoverage] = []
        category_present = sum(1 for product in products if product.category)
        for field in coverage:
            if field.field != "category" or field.source_column is not None:
                result.append(field)
                continue
            result.append(
                field.model_copy(
                    update={
                        "source_column": "строки-разделы",
                        "present_rows": category_present,
                        "missing_rows": max(len(products) - category_present, 0),
                        "coverage_percent": round(category_present / len(products) * 100, 2),
                    }
                )
            )
        return result

    def _optional_text(self, row: pd.Series, mapping: dict[str, str], field: str) -> str | None:
        column = mapping.get(field)
        if column is None:
            return None
        return self._text(row.get(column)) or None

    def _text(self, value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def _has_value(self, value: object) -> bool:
        return bool(self._text(value))

    def _number(self, value: object) -> float | None:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, str):
            normalized = value.replace("\u00a0", "").replace(" ", "").replace(",", ".")
            if not normalized:
                return None
            value = normalized
        try:
            return float(value)
        except (TypeError, ValueError):
            if isinstance(value, str):
                match = search(r"-?\d+(?:[.,]\d+)?", value)
                if match:
                    return float(match.group(0).replace(",", "."))
            return None

    def _stock_value(self, row: pd.Series, stock_columns: list[str]) -> float | None:
        values = [self._stock_number(row.get(column)) for column in stock_columns]
        available = [value for value in values if value is not None]
        if not available:
            return None
        return round(sum(available), 3)

    def _stock_number(self, value: object) -> float | None:
        numeric = self._number(value)
        if numeric is not None:
            return max(numeric, 0.0)
        text = self._text(value).lower().replace("ё", "е")
        if not text:
            return None
        if any(
            marker in text
            for marker in ("нет в наличии", "нет", "под заказ", "ожидается", "отсутствует")
        ):
            return 0.0
        match = search(r"\d+(?:[\s\u00a0]*[.,]\d+)?", text)
        if match:
            normalized = match.group(0).replace("\u00a0", "").replace(" ", "")
            return max(float(normalized.replace(",", ".")), 0.0)
        if any(marker in text for marker in ("в наличии", "есть", "много")):
            return 1.0
        return None

    def _excel_engine(self, content: bytes, filename: str) -> str:
        lower_name = filename.lower()
        if lower_name.endswith(".xls") and not lower_name.endswith(".xlsx"):
            return "xlrd"
        if content.startswith(b"\xd0\xcf\x11\xe0"):
            return "xlrd"
        return "openpyxl"
