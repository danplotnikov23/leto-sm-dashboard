from io import BytesIO

import pandas as pd

from app.ingestion.excel_importer import ExcelImportService


def test_import_excel_detects_columns_and_deduplicates() -> None:
    frame = pd.DataFrame(
        [
            {
                "Артикул поставщика": "A-1",
                "Наименование": "Клей плиточный",
                "Группа": "Стройматериалы",
                "Закупочная цена": "1 000,50",
                "Вес кг": 25,
                "Длина см": 40,
                "Ширина см": 30,
                "Высота см": 10,
                "Остатки": 12,
                "Бренд": "Лето",
            },
            {
                "Артикул поставщика": "A-1",
                "Наименование": "Клей плиточный дубль",
                "Группа": "Стройматериалы",
                "Закупочная цена": 990,
            },
        ]
    )
    version = ExcelImportService().import_frame(frame, "prices.xlsx")

    assert version.total_rows == 2
    assert version.accepted_rows == 1
    assert version.products[0].purchase_price_vat_included == 1000.5
    assert version.products[0].dimensions.volume_liters == 12
    assert version.detected_columns["supplier_article"] == "Артикул поставщика"
    assert version.error_count == 0
    assert version.warning_count >= 1
    assert any(
        field.field == "stock" and field.coverage_percent == 50 for field in version.field_coverage
    )
    assert any(issue.message == "Дубль товара пропущен." for issue in version.issues)


def test_import_bytes_reports_missing_required_columns() -> None:
    output = BytesIO()
    pd.DataFrame([{"Название": "Без артикула"}]).to_excel(output, index=False)

    version = ExcelImportService().import_bytes(output.getvalue(), "broken.xlsx")

    assert version.accepted_rows == 0
    assert {issue.field for issue in version.issues} >= {
        "supplier_article",
        "purchase_price_vat_included",
    }


def test_import_adds_quality_warnings_for_missing_operational_fields() -> None:
    frame = pd.DataFrame(
        [
            {
                "Артикул": "A-2",
                "Название": "Грунтовка",
                "Закупочная цена": 300,
            }
        ]
    )

    version = ExcelImportService().import_frame(frame, "minimal.xlsx")

    assert version.accepted_rows == 1
    assert version.rejected_rows == 0
    assert any(issue.field == "category" for issue in version.issues)
    assert any(issue.field == "weight_kg" for issue in version.issues)
    assert any(issue.field == "dimensions" for issue in version.issues)
    assert any(issue.field == "stock" for issue in version.issues)


def test_import_deduplicates_by_article_even_when_barcode_is_present() -> None:
    frame = pd.DataFrame(
        [
            {
                "Артикул": "A-1",
                "Название": "Цемент",
                "Закупочная цена": 300,
                "Штрихкод": 4600000000011,
            },
            {
                "Артикул": "A-1",
                "Название": "Цемент дубль",
                "Закупочная цена": 290,
            },
        ]
    )

    version = ExcelImportService().import_frame(frame, "dupes.xlsx")

    assert version.accepted_rows == 1
    assert version.products[0].barcode == "4600000000011"
    assert any(issue.message == "Дубль товара пропущен." for issue in version.issues)


def test_import_detects_header_inside_supplier_price_and_uses_section_category() -> None:
    frame = pd.DataFrame(
        [
            [None, None, None, None, None, None],
            ["ПРАЙС-ЛИСТ", None, None, None, None, None],
            ["Стоимость товаров указана в рублях", None, None, None, None, None],
            [None, None, None, None, None, None],
            ["Артикул", "Код", "Номенклатура", "Ед. изм", "Цена", "Остатки"],
            ["Электрика", None, None, None, None, None],
            ["Бра к спотам FERON", None, None, None, None, None],
            ["41489", "10685381", "Светильник СПОТЫ ML232", "шт", "1713.4", "1"],
        ]
    )

    version = ExcelImportService().import_frame(frame, "price_export.xlsx")

    assert version.total_rows == 3
    assert version.accepted_rows == 1
    assert version.products[0].supplier_article == "41489"
    assert version.products[0].title == "Светильник СПОТЫ ML232"
    assert version.products[0].category == "Бра к спотам FERON"
    assert version.products[0].stock == 1
    assert version.products[0].purchase_price_vat_included == 1713.4
    assert any(
        field.field == "category"
        and field.source_column == "строки-разделы"
        and field.coverage_percent == 100
        for field in version.field_coverage
    )


def test_import_detects_supplier_stock_alias_and_text_lower_bound() -> None:
    frame = pd.DataFrame(
        [
            {
                "Код": "S-1",
                "Номенклатура": "Смеситель",
                "Цена": 1500,
                "Доступное количество": ">10 шт.",
            },
            {
                "Код": "S-2",
                "Номенклатура": "Раковина",
                "Цена": 3000,
                "Доступное количество": "под заказ",
            },
        ]
    )

    version = ExcelImportService().import_frame(frame, "supplier.xlsx")

    assert [product.stock for product in version.products] == [10, 0]
    stock_coverage = next(field for field in version.field_coverage if field.field == "stock")
    assert stock_coverage.source_column == "Доступное количество"
    assert stock_coverage.coverage_percent == 100


def test_import_sums_separate_warehouse_stock_columns_without_total() -> None:
    frame = pd.DataFrame(
        [
            {
                "Артикул": "W-1",
                "Название": "Лампа",
                "Закупочная цена": 200,
                "Остаток Вологда": 3,
                "Остаток Череповец": 4,
            }
        ]
    )

    version = ExcelImportService().import_frame(frame, "warehouses.xlsx")

    assert version.products[0].stock == 7
    stock_coverage = next(field for field in version.field_coverage if field.field == "stock")
    assert stock_coverage.source_column == "Остаток Вологда + Остаток Череповец"


def test_import_prefers_total_stock_over_warehouse_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                "Артикул": "T-1",
                "Название": "Розетка",
                "Цена": 400,
                "Остаток Вологда": 3,
                "Остаток Череповец": 4,
                "Остаток всего": 7,
            }
        ]
    )

    version = ExcelImportService().import_frame(frame, "total-stock.xlsx")

    assert version.products[0].stock == 7
    stock_coverage = next(field for field in version.field_coverage if field.field == "stock")
    assert stock_coverage.source_column == "Остаток всего"


def test_import_reads_all_pro_brite_sheets_and_carries_variant_title() -> None:
    output = BytesIO()
    cleaning = pd.DataFrame(
        [
            {
                "Наименование": "NUTRAL",
                "Кол-во в уп.": 4,
                "Объём тары (Вес), л (кг)": 5,
                "АРТИКУЛ": "002-5",
                "Для оптовиков и торговых сетей сумма от 150 тыс./руб. мес.": 800.37,
            },
            {
                "Наименование": None,
                "Кол-во в уп.": 12,
                "Объём тары (Вес), л (кг)": "0,5 (тр)",
                "АРТИКУЛ": "002-05",
                "Для оптовиков и торговых сетей сумма от 150 тыс./руб. мес.": 138.47,
            },
        ]
    )
    retail = pd.DataFrame(
        [
            {
                "продукт": "Освежитель воздуха",
                "артикул": "311-037",
                "фасовка": "370 мл.",
                "Количество в упаковке": 6,
                "ОПТ": 123.86,
            }
        ]
    )
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        cleaning.to_excel(writer, sheet_name="PB Клининг", index=False)
        retail.to_excel(writer, sheet_name="RTL", index=False)

    version = ExcelImportService().import_bytes(output.getvalue(), "pro-brite.xlsx")

    assert version.accepted_rows == 3
    products = {product.supplier_article: product for product in version.products}
    assert products["002-5"].title == "NUTRAL"
    assert products["002-05"].title == "NUTRAL"
    assert products["002-05"].package == "0,5 (тр)"
    assert products["002-05"].weight_kg == 0.5
    assert products["002-05"].multiplicity == 12
    assert products["002-05"].purchase_price_vat_included == 138.47
    assert products["311-037"].title == "Освежитель воздуха"
    assert products["311-037"].package == "370 мл."
    assert products["311-037"].stock is None
    stock_coverage = next(field for field in version.field_coverage if field.field == "stock")
    assert stock_coverage.source_column is None
    assert stock_coverage.coverage_percent == 0


def test_import_supports_krepezh_price_layout_with_title_code_unit_price() -> None:
    frame = pd.DataFrame(
        [
            [None, None, None, None],
            ["Прайс-лист от 18 мая 2026 г.", None, None, None],
            ['Организация: ООО "КРЕПЕЖ"', None, None, None],
            ["Номенклатура", "Код", "Единица измерения", "Цена"],
            ["Инструмент", None, None, None],
            ["Абразивы", None, None, None],
            ["Бруски, сегменты", None, None, None],
            ['Брусок 230мм "Лодочка" 38325', "00006933", "шт", 110],
            ["Брусок абразивный 250x33x17 мм, P120 32048", "БП-00001154", "шт", 277],
            ["Зачистные", None, None, None],
            ["Круг зачистной 115х6,0х22", "00002316", "шт", 75],
        ]
    )

    version = ExcelImportService().import_frame(frame, "Прайс-лист ООО КРЕПЕЖ июнь.xls")

    assert version.total_rows == 7
    assert version.section_rows == 4
    assert version.accepted_rows == 3
    assert version.products[0].supplier_article == "00006933"
    assert version.products[0].title == 'Брусок 230мм "Лодочка" 38325'
    assert version.products[0].purchase_price_vat_included == 110
    assert version.products[0].category == "Бруски, сегменты"
    assert version.products[2].category == "Зачистные"
    assert version.detected_columns["title"] == "Номенклатура"
    assert version.detected_columns["supplier_article"] == "Код"
    assert version.detected_columns["purchase_price_vat_included"] == "Цена"
