import pandas as pd

from app.api.routes import _normalized_competitor_offer
from app.domain.models import CompetitorOffer, SupplierProduct
from app.services.competitor_import import CompetitorImportService


def test_ozon_competitor_export_is_matched_to_supplier_products() -> None:
    products = [
        SupplierProduct(
            supplier_article="N-1",
            title="Гвозди строительные 1,2х16 черные 200г",
            category="Строительные",
            purchase_price_vat_included=39,
        )
    ]
    frame = pd.DataFrame(
        [
            {
                "Название товара": "Гвозди Стройметиз строительные 1.2x16, 200 гр.",
                "Категория": "Гвозди",
                "Заказано товаров": "1326",
                "Средняя цена покупки": "602 ₽",
                "Самая низкая цена": "239 ₽",
                "Доля выкупа": "95,3%",
            }
        ]
    )
    content = _xlsx_bytes(frame)

    result, matches = CompetitorImportService().import_bytes(
        content,
        "competitors.xlsx",
        products,
    )

    assert result.imported_rows == 1
    assert result.matched_products == 1
    match = matches[products[0].id]
    assert match.price_vat_included == 239
    assert match.orders_count == 1326
    assert match.buyout_rate == 0.953
    assert match.avg_purchase_price == 602


def test_visible_table_import_uses_average_price_when_min_price_is_noise() -> None:
    offer = CompetitorOffer(
        title="Жидкие гвозди клей прозрачный TYTAN Classic FIX 310мл",
        price_vat_included=1,
        avg_purchase_price=601,
    )

    normalized = _normalized_competitor_offer(offer)

    assert normalized.price_vat_included == 601
    assert normalized.source == "api"


def test_competitor_match_penalizes_wrong_pack_size() -> None:
    product = SupplierProduct(
        supplier_article="N-2",
        title="Гвозди ершёные 2,8х40 цинк 250г",
        category="Гвозди",
        purchase_price_vat_included=64,
    )
    offers = [
        CompetitorOffer(
            title="Гвозди 100мм 5кг строительные черные",
            price_vat_included=3794,
            orders_count=100,
        ),
        CompetitorOffer(
            title="Гвозди ершеные 2.8х40 мм оцинкованные 250 г",
            price_vat_included=399,
            orders_count=10,
        ),
    ]

    matches, issues = CompetitorImportService().match_offers([*offers], [product])

    assert issues == []
    assert matches[product.id].price_vat_included == 399


def test_competitor_match_rejects_partial_dimension_overlap() -> None:
    product = SupplierProduct(
        supplier_article="N-3",
        title="Гвозди ершёные 2,8х40 цинк 250г",
        category="Гвозди",
        purchase_price_vat_included=64,
    )
    offer = CompetitorOffer(
        title="Реечные гвозди D34 PAULT 64x2.8 мм Ri EG ершеные, оцинкованные",
        price_vat_included=2369,
        orders_count=100,
    )

    matches, issues = CompetitorImportService().match_offers([offer], [product])

    assert matches == {}
    assert issues[0].severity == "warning"


def _xlsx_bytes(frame: pd.DataFrame) -> bytes:
    from io import BytesIO

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
    return output.getvalue()
