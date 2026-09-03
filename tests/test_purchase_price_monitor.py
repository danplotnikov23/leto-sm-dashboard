from app.domain.unitka import UnitkaRow
from app.services.purchase_price_monitor import reconcile_purchase_prices
from app.services.tdcsm_client import TdcsmClient, TdcsmStockInfo


def _supplier(idcode: str, price: float) -> TdcsmStockInfo:
    return TdcsmStockInfo(
        idcode=idcode,
        store=10,
        sellable_stock=10,
        contain=1,
        only_contain_order=False,
        name=f"Товар {idcode}",
        discontinued=False,
        price_per_base_unit=price,
        purchase_price=price,
    )


def test_reconcile_purchase_prices_only_counts_published_offer_ids() -> None:
    rows = [
        UnitkaRow(id="unitka-a", supplier_article="A", title="A", purchase_price_vat_included=100),
        UnitkaRow(id="unitka-b", supplier_article="B", title="B", purchase_price_vat_included=300),
    ]

    snapshot = reconcile_purchase_prices(
        ["A", "MISSING", "A"],
        {"A": _supplier("A", 125)},
        rows,
    )

    assert snapshot.total_published == 2
    assert snapshot.matched_to_unitka == 1
    assert snapshot.supplier_not_found == 1
    assert snapshot.diff_count == 1
    comparison = next(row for row in snapshot.rows if row.offer_id == "A")
    assert comparison.unitka_row_id == "unitka-a"
    assert comparison.current_purchase_price == 100
    assert comparison.supplier_purchase_price == 125
    assert comparison.delta == 25


def test_reconcile_does_not_mark_equal_price_as_difference() -> None:
    row = UnitkaRow(id="unitka-a", supplier_article="A", title="A", purchase_price_vat_included=125)
    snapshot = reconcile_purchase_prices(["A"], {"A": _supplier("A", 125)}, [row])

    assert snapshot.diff_count == 0
    assert snapshot.rows[0].delta == 0


def test_tdcsm_price_is_not_multiplied_by_logistics_contain() -> None:
    product = TdcsmClient._to_stock_info(
        {
            "idcode": "00002735",
            "name": "Саморез &#215;",
            "price": 603,
            "contain": 16,
            "store": 336,
            "only_contain_order": False,
        }
    )

    assert product.purchase_price == 603
    assert product.contain == 16
    assert product.sellable_stock == 336
    assert product.name == "Саморез ×"
