from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.api import routes
from app.db.sqlite import SQLiteStore
from app.main import app


def _xlsx(rows: list[dict[str, object]]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False)
    return output.getvalue()


def test_shortlist_is_matrix_independent_from_active_price_import(tmp_path) -> None:
    original_repository = routes.repository
    routes.repository = SQLiteStore(f"sqlite:///{tmp_path / 'matrix.db'}")
    client = TestClient(app)
    try:
        first_response = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "first.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "A-1",
                                "Название": "Товар матрицы",
                                "Категория": "Сантехника",
                                "Закупочная цена": 1000,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert first_response.status_code == 200
        product_id = first_response.json()["products"][0]["id"]

        add_response = client.post(
            f"/api/shortlist/products/{product_id}",
            json={
                "group_name": "Сантехника",
                "offer_quantity": 2,
                "purchase_price_vat_included": 750,
                "sale_price_vat_included": 2500,
                "length_cm": 40,
                "width_cm": 20,
                "height_cm": 10,
                "seller_bonus_percent": 35,
                "advertising_drr_percent": 9,
                "package_cost": 40,
                "fulfillment_processing_cost": 60,
                "planned_sales_qty": 5,
            },
        )
        assert add_response.status_code == 200
        assert add_response.json()["analysis"]["product"]["dimensions"]["volume_liters"] == 8
        assert add_response.json()["analysis"]["economics"]["purchase_price_vat_included"] == 1500

        second_response = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "second.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "B-1",
                                "Название": "Другой прайс",
                                "Категория": "Электрика",
                                "Закупочная цена": 2000,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert second_response.status_code == 200

        shortlist_response = client.get("/api/shortlist")
        assert shortlist_response.status_code == 200
        payload = shortlist_response.json()
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["entry"]["supplier_article"] == "A-1"
        assert item["entry"]["source_import_filename"] == "first.xlsx"
        assert item["analysis"]["product"]["title"] == "Товар матрицы"
        assert item["entry"]["purchase_price_vat_included"] == 750
        assert item["entry"]["offer_quantity"] == 2
        assert item["analysis"]["economics"]["purchase_price_vat_included"] == 1500
        assert item["analysis"]["economics"]["seller_bonus_percent"] == 35
        assert item["analysis"]["economics"]["advertising_drr_percent"] == 9
        assert item["analysis"]["economics"]["package_cost"] == 40
        assert item["analysis"]["economics"]["fulfillment_processing_cost"] == 60

        export_json_response = client.get("/api/exports/shortlist.json")
        assert export_json_response.status_code == 200
        assert export_json_response.json()["items"][0]["entry"]["product_snapshot"] is not None

        export_excel_response = client.get("/api/exports/shortlist.xlsx")
        assert export_excel_response.status_code == 200
        assert len(export_excel_response.content) > 1000

        delete_response = client.delete(f"/api/shortlist/products/{product_id}")
        assert delete_response.status_code == 204
        assert client.get("/api/shortlist").json()["items"] == []
    finally:
        routes.repository = original_repository


def test_shortlist_refreshes_only_stock_from_new_matching_supplier_price(tmp_path) -> None:
    original_repository = routes.repository
    routes.repository = SQLiteStore(f"sqlite:///{tmp_path / 'stock-refresh.db'}")
    client = TestClient(app)
    try:
        first = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "supplier-old.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "A-1",
                                "Название": "Товар матрицы",
                                "Закупочная цена": 1000,
                                "Остаток": 12,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        product_id = first.json()["products"][0]["id"]
        added = client.post(
            f"/api/shortlist/products/{product_id}",
            json={"purchase_price_vat_included": 850, "sale_price_vat_included": 2500},
        )
        assert added.status_code == 200
        assert added.json()["analysis"]["product"]["stock"] == 12

        refreshed = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "supplier-new.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "A-1",
                                "Название": "Товар матрицы",
                                "Закупочная цена": 1100,
                                "Остаток": 0,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert refreshed.status_code == 200

        refresh_response = client.post("/api/shortlist/refresh-stocks")
        assert refresh_response.status_code == 200
        assert refresh_response.json()["matched"] == 1
        assert refresh_response.json()["updated"] == 1
        assert refresh_response.json()["unmatched"] == 0
        item = refresh_response.json()["items"][0]
        assert item["analysis"]["product"]["stock"] == 0
        assert item["entry"]["purchase_price_vat_included"] == 850
        assert item["analysis"]["economics"]["recommendation"] == "Не заводить"
    finally:
        routes.repository = original_repository


def test_add_shortlist_recovers_from_stale_product_id_after_price_reload(tmp_path) -> None:
    original_repository = routes.repository
    routes.repository = SQLiteStore(f"sqlite:///{tmp_path / 'stale-id.db'}")
    client = TestClient(app)
    try:
        first = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "old.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "C0045552",
                                "Название": "Фонарь прожектор Трофи",
                                "Цена": 1005,
                                "Остаток": 3,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        stale_id = first.json()["products"][0]["id"]

        second = client.post(
            "/api/imports/prices",
            files={
                "file": (
                    "new.xlsx",
                    _xlsx(
                        [
                            {
                                "Артикул": "C0045552",
                                "Название": "Фонарь прожектор Трофи",
                                "Цена": 990,
                                "Остаток": 4,
                            }
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        current_id = second.json()["products"][0]["id"]
        assert current_id == stale_id

        added = client.post(
            f"/api/shortlist/products/{stale_id}",
            json={
                "supplier_article": "C0045552",
                "product_title": "Фонарь прожектор Трофи",
                "sale_price_vat_included": 2000,
            },
        )

        assert added.status_code == 200
        assert added.json()["analysis"]["product"]["id"] == current_id
        assert added.json()["analysis"]["product"]["stock"] == 4
    finally:
        routes.repository = original_repository
