from pathlib import Path

import pandas as pd

from app.db.sqlite import SQLiteStore, sqlite_path
from app.domain.models import CompetitorOffer, DataSource, ShortlistEntry
from app.ingestion.excel_importer import ExcelImportService


def test_saving_imports_from_different_suppliers_builds_unified_catalog(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path / 'catalog.db'}")
    importer = ExcelImportService()

    first = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "A-1",
                    "Название": "Старый товар",
                    "Закупочная цена": 100,
                }
            ]
        ),
        "first.xlsx",
        "Поставщик А",
    )
    second = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "B-1",
                    "Название": "Новый товар",
                    "Закупочная цена": 200,
                }
            ]
        ),
        "second.xlsx",
        "Поставщик Б",
    )

    store.save_import(first)
    store.save_import(second)

    products = store.list_products()
    versions = store.list_versions()
    assert [product.supplier_article for product in products] == ["A-1", "B-1"]
    assert {product.supplier_name for product in products} == {"Поставщик А", "Поставщик Б"}
    assert len(versions) == 2


def test_reimport_updates_same_supplier_and_preserves_product_id(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path / 'catalog.db'}")
    importer = ExcelImportService()
    first = importer.import_frame(
        pd.DataFrame([{"Артикул": "A-1", "Название": "Товар", "Цена": 100}]),
        "old.xlsx",
        "Поставщик",
    )
    saved_first = store.save_import(first)
    second = importer.import_frame(
        pd.DataFrame([{"Артикул": "A-1", "Название": "Товар", "Цена": 90}]),
        "new.xlsx",
        "Поставщик",
    )
    saved_second = store.save_import(second)

    assert saved_second.products[0].id == saved_first.products[0].id
    assert len(store.list_products()) == 1
    assert store.list_products()[0].purchase_price_vat_included == 90


def test_competitor_override_is_kept_by_supplier_article_after_reimport(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path / 'catalog.db'}")
    importer = ExcelImportService()

    first = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "A-1",
                    "Название": "Гвозди 2x40",
                    "Закупочная цена": 39,
                }
            ]
        ),
        "first.xlsx",
    )
    store.save_import(first)
    first_product = store.list_products()[0]
    store.save_competitor_override(
        first_product,
        CompetitorOffer(
            title="Гвозди конкурент",
            price_vat_included=239,
            url="https://www.ozon.ru/product/164844946/",
            match_type="analog",
        ),
    )

    second = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "A-1",
                    "Название": "Гвозди 2x40 новая строка",
                    "Закупочная цена": 40,
                }
            ]
        ),
        "second.xlsx",
    )
    store.save_import(second)

    second_product = store.list_products()[0]
    snapshot = store.get_competitor_snapshot(second_product)

    assert snapshot.source == DataSource.MANUAL
    assert snapshot.min_price == 239
    assert snapshot.leader_url == "https://www.ozon.ru/product/164844946/"
    assert snapshot.leader is not None
    assert snapshot.leader.match_type == "analog"


def test_shortlist_snapshot_survives_active_catalog_replacement(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path / 'catalog.db'}")
    importer = ExcelImportService()

    first = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "A-1",
                    "Название": "Товар из первого прайса",
                    "Закупочная цена": 100,
                }
            ]
        ),
        "first.xlsx",
    )
    store.save_import(first)
    first_product = store.list_products()[0]
    store.save_shortlist_entry(
        ShortlistEntry(
            supplier_article=first_product.supplier_article,
            product_id=first_product.id,
            product_snapshot=first_product,
            source_import_filename="first.xlsx",
            sale_price_vat_included=500,
        )
    )

    second = importer.import_frame(
        pd.DataFrame(
            [
                {
                    "Артикул": "B-1",
                    "Название": "Товар из второго прайса",
                    "Закупочная цена": 200,
                }
            ]
        ),
        "second.xlsx",
    )
    store.save_import(second)

    entries = store.list_shortlist_entries()

    assert len(entries) == 1
    assert entries[0].supplier_article == "A-1"
    assert entries[0].product_snapshot is not None
    assert entries[0].product_snapshot.title == "Товар из первого прайса"
    assert store.get_shortlist_entry_by_product_id(first_product.id) is not None


def test_relative_sqlite_path_is_resolved_from_backend_dir() -> None:
    path = sqlite_path("sqlite:///./leto_bi.db")

    assert path.is_absolute()
    assert path == Path(__file__).resolve().parents[1] / "backend" / "leto_bi.db"
