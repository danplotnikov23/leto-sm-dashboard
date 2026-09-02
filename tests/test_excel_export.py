from io import BytesIO

from openpyxl import load_workbook

from app.domain.models import Dimensions, ShortlistEntry, ShortlistItem, SupplierProduct
from app.services.analysis import ProductAnalysisService
from app.services.excel_export import UnitEconomicsExcelExporter


def product(price: float = 1000) -> SupplierProduct:
    return SupplierProduct(
        supplier_article="A-1",
        title="Клей плиточный",
        category="Стройматериалы",
        purchase_price_vat_included=price,
        weight_kg=25,
        dimensions=Dimensions(length_cm=40, width_cm=30, height_cm=10),
    )


def test_shortlist_export_contains_editable_formula_model() -> None:
    analysis = ProductAnalysisService().analyze_product(
        product(500),
        sale_price_vat_included=2000,
    )
    entry = ShortlistEntry(
        supplier_article=analysis.product.supplier_article,
        product_id=analysis.product.id,
        group_name="Крепеж",
        subgroup_name="Тест",
        sale_price_vat_included=2000,
        planned_sales_qty=10,
        sold_qty=2,
    )

    content = UnitEconomicsExcelExporter().export_shortlist(
        [ShortlistItem(entry=entry, analysis=analysis)]
    )

    workbook = load_workbook(BytesIO(content), data_only=False)
    sheet = workbook["Отбор"]

    assert workbook.calculation.calcMode == "auto"
    assert workbook.calculation.fullCalcOnLoad is True
    assert sheet["N4"].value == 2000
    assert sheet["Q4"].value == "=MAX(N4-AH4,0)"
    assert sheet["AI4"].value == "=Q4+AH4+N4*AQ4+N4*AR4"
    assert str(sheet["AF4"].value).startswith("=AI4-SUM(R4:W4)")
    assert sheet["S4"].value == "=IF(AY4>0,AX4/AY4,0)"
    assert sheet["AE4"].value == "=IF(AY4>0,AW4/AY4,0)"
    assert sheet["AO4"].value == 1
    assert sheet["BD4"].value == "=R4/AO4"
    assert sheet["BG4"].value == "=N4*BE4"
    assert sheet["BM4"].value == "Крепеж"
    assert sheet["BN4"].value == "Тест"
    assert sheet["BO4"].value == 40
    assert sheet["BP4"].value == 30
    assert sheet["BQ4"].value == 10
    assert sheet["V3"].value == 0.04
    assert sheet["W3"].value == 0.0245
    assert sheet["AA3"].value == 0.01
    assert sheet["AD3"].value == 0.07
    assert sheet["AT4"].value == 0.12
    assert len(sheet.data_validations.dataValidation) == 1
