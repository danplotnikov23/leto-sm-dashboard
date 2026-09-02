from app.domain.stock import StockStatus
from app.services.stock_monitor import classify


def test_classify_critical_when_supplier_has_zero() -> None:
    assert classify(ozon_stock=5, supplier_stock=0, supplier_found=True, threshold=10) == (
        StockStatus.CRITICAL
    )


def test_classify_unknown_when_supplier_not_found() -> None:
    assert classify(ozon_stock=5, supplier_stock=None, supplier_found=False, threshold=10) == (
        StockStatus.UNKNOWN
    )


def test_classify_restock_when_ozon_zero_but_supplier_has_stock() -> None:
    assert classify(ozon_stock=0, supplier_stock=50, supplier_found=True, threshold=10) == (
        StockStatus.RESTOCK
    )


def test_classify_low_when_supplier_below_threshold() -> None:
    assert classify(ozon_stock=3, supplier_stock=5, supplier_found=True, threshold=10) == (
        StockStatus.LOW
    )


def test_classify_mismatch_when_ozon_overstates_supplier() -> None:
    # На Ozon больше, чем реально есть у поставщика — риск продать "в минус".
    assert classify(ozon_stock=20, supplier_stock=15, supplier_found=True, threshold=10) == (
        StockStatus.MISMATCH
    )


def test_classify_ok_when_ozon_within_supplier_stock() -> None:
    assert classify(ozon_stock=10, supplier_stock=15, supplier_found=True, threshold=10) == (
        StockStatus.OK
    )


def test_classify_restock_takes_priority_over_low() -> None:
    # ozon_stock == 0 должен давать restock, даже если supplier_stock тоже ниже порога.
    assert classify(ozon_stock=0, supplier_stock=3, supplier_found=True, threshold=10) == (
        StockStatus.RESTOCK
    )
