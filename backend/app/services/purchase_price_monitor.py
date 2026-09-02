"""Сверка закупочных цен: Ozon offer_id -> tdcsm.ru -> живая Юнитка.

Ozon — единственный источник списка опубликованных SKU. Поставщик возвращает
цену за базовую единицу и кратность, поэтому ``TdcsmClient`` уже передаёт сюда
готовую цену продаваемой единицы ``purchase_price``. Excel не участвует в этом
процессе и никогда не изменяется.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.domain.purchase_prices import (
    PurchasePriceApplyResult,
    PurchasePriceRow,
    PurchasePriceSnapshot,
)
from app.domain.unitka import UnitkaRow
from app.services.ozon_client import OzonCredentials, OzonSellerClient
from app.services.tdcsm_client import TdcsmClient, TdcsmStockInfo
from app.services.unitka_storage import list_rows, update_row


class PurchasePriceMonitorNotConfigured(RuntimeError):
    pass


def _require_credentials(settings: Settings) -> OzonCredentials:
    if not settings.ozon_client_id or not settings.ozon_api_key:
        msg = "Не заданы OZON_CLIENT_ID / OZON_API_KEY в backend/.env."
        raise PurchasePriceMonitorNotConfigured(msg)
    return OzonCredentials(client_id=settings.ozon_client_id, api_key=settings.ozon_api_key)


async def _list_all_offer_ids(client: OzonSellerClient) -> list[str]:
    offer_ids: list[str] = []
    last_id = ""
    while True:
        data = await client.list_products(limit=100, visibility="ALL", last_id=last_id)
        result = data.get("result", {})
        if not isinstance(result, dict):
            break
        chunk = result.get("items", [])
        if not isinstance(chunk, list):
            break
        offer_ids.extend(
            item["offer_id"]
            for item in chunk
            if isinstance(item, dict) and isinstance(item.get("offer_id"), str) and item["offer_id"]
        )
        next_last_id = result.get("last_id", "")
        if not chunk or not isinstance(next_last_id, str) or not next_last_id:
            break
        last_id = next_last_id
    return offer_ids


def reconcile_purchase_prices(
    offer_ids: list[str],
    supplier_data: dict[str, TdcsmStockInfo],
    unitka_rows: list[UnitkaRow],
) -> PurchasePriceSnapshot:
    """Собирает детерминированный снимок, без HTTP и без записи в БД."""
    rows_by_article = {row.supplier_article: row for row in unitka_rows}
    rows: list[PurchasePriceRow] = []
    for offer_id in sorted(set(offer_ids)):
        unitka_row = rows_by_article.get(offer_id)
        supplier = supplier_data.get(offer_id)
        current_price = unitka_row.purchase_price_vat_included if unitka_row else None
        supplier_price = supplier.purchase_price if supplier else None
        delta = (
            round(supplier_price - current_price, 2)
            if supplier_price is not None and current_price is not None
            else None
        )
        rows.append(
            PurchasePriceRow(
                offer_id=offer_id,
                supplier_name=supplier.name if supplier else None,
                unitka_row_id=unitka_row.id if unitka_row else None,
                unitka_title=unitka_row.title if unitka_row else None,
                current_purchase_price=current_price,
                supplier_purchase_price=supplier_price,
                delta=delta,
                supplier_found=supplier is not None,
                in_unitka=unitka_row is not None,
            )
        )

    return PurchasePriceSnapshot(
        checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
        total_published=len(rows),
        matched_to_unitka=sum(row.in_unitka for row in rows),
        supplier_not_found=sum(not row.supplier_found for row in rows),
        diff_count=sum(row.delta is not None and row.delta != 0 for row in rows),
        rows=rows,
    )


async def refresh_purchase_prices(settings: Settings) -> PurchasePriceSnapshot:
    credentials = _require_credentials(settings)
    ozon_client = OzonSellerClient(credentials, base_url=settings.ozon_api_base_url)
    offer_ids = await _list_all_offer_ids(ozon_client)
    supplier_client = TdcsmClient(base_url=settings.tdcsm_api_base_url)
    supplier_data = await supplier_client.stock_for_idcodes(offer_ids)
    return reconcile_purchase_prices(offer_ids, supplier_data, list_rows())


async def apply_purchase_prices(settings: Settings) -> PurchasePriceApplyResult:
    """Повторно читает источники и обновляет только реально изменившиеся строки.

    Повторная сверка защищает от устаревшей вкладки браузера: в базу попадёт
    цена, которую tdcsm.ru отдал непосредственно в момент явного применения.
    """
    snapshot = await refresh_purchase_prices(settings)
    by_id = {row.id: row for row in list_rows()}
    updated = 0
    for comparison in snapshot.rows:
        if (
            comparison.unitka_row_id is None
            or comparison.supplier_purchase_price is None
            or comparison.delta in (None, 0)
        ):
            continue
        unitka_row = by_id.get(comparison.unitka_row_id)
        if unitka_row is None:
            continue
        update_row(
            unitka_row.id,
            unitka_row.model_copy(
                update={"purchase_price_vat_included": comparison.supplier_purchase_price}
            ),
        )
        updated += 1

    return PurchasePriceApplyResult(
        updated=updated,
        ok=True,
        message=(
            "Расхождений нет — обновлять нечего."
            if updated == 0
            else f"Обновлены закупочные цены в живой Юнитке: {updated} SKU."
        ),
    )
