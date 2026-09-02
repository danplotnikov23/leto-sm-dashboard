"""Сверка остатков Ozon vs поставщик tdcsm.ru — перенос projects/stock-monitor/checker.py.

Логика `classify()` перенесена дословно (см. её же комментарии) — это уже проверенный
в бою код ежедневного Telegram-бота «Остатки Лето СМ». Здесь он вызывается по кнопке
«Обновить сейчас» из платформы вместо cron; отправка в Telegram остаётся отдельным,
не тронутым скриптом `projects/stock-monitor/checker.py` — эта функция её не дублирует.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.domain.stock import StockApplyResult, StockRow, StockSnapshot, StockStatus
from app.services.ozon_client import OzonCredentials, OzonSellerClient
from app.services.stock_storage import latest_snapshot, save_snapshot
from app.services.tdcsm_client import TdcsmClient


class StockMonitorNotConfigured(RuntimeError):
    pass


def _require_credentials(settings: Settings) -> OzonCredentials:
    if not settings.own_ozon_client_id or not settings.own_ozon_api_key:
        msg = (
            "Не заданы OWN_OZON_CLIENT_ID / OWN_OZON_API_KEY — это ключи собственного "
            "кабинета Ozon (Лето СМ), отдельные от OZON_CLIENT_ID бенчмарк-аккаунта."
        )
        raise StockMonitorNotConfigured(msg)
    return OzonCredentials(client_id=settings.own_ozon_client_id, api_key=settings.own_ozon_api_key)


def classify(
    ozon_stock: int,
    supplier_stock: int | None,
    supplier_found: bool,
    threshold: int,
) -> StockStatus:
    if not supplier_found:
        return StockStatus.UNKNOWN
    if supplier_stock == 0:
        return StockStatus.CRITICAL
    if ozon_stock == 0:
        # У поставщика остаток появился, а на Ozon всё ещё 0 — карточка не продаётся,
        # хотя реально может. Не путать с "critical" (там наоборот, у поставщика пусто).
        return StockStatus.RESTOCK
    if supplier_stock is not None and supplier_stock < threshold:
        return StockStatus.LOW
    if supplier_stock is not None and ozon_stock > supplier_stock:
        # На Ozon стоит больше, чем реально есть у поставщика — риск продать "в минус".
        return StockStatus.MISMATCH
    return StockStatus.OK


async def _list_all_offer_ids(client: OzonSellerClient) -> list[str]:
    offer_ids: list[str] = []
    last_id = ""
    while True:
        data = await client.list_products(limit=100, visibility="ALL", last_id=last_id)
        result = data.get("result", {})
        chunk = result.get("items", [])
        offer_ids.extend(it["offer_id"] for it in chunk if it.get("offer_id"))
        last_id = result.get("last_id", "")
        if not chunk or not last_id:
            break
    return offer_ids


async def _stock_for_offer_ids(client: OzonSellerClient, offer_ids: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for i in range(0, len(offer_ids), 100):
        chunk = offer_ids[i : i + 100]
        data = await client.get_stocks_by_offer_ids(chunk)
        items = data.get("items") or data.get("result", {}).get("items") or []
        for it in items:
            offer_id = it.get("offer_id")
            stocks = (it.get("stocks") or {}).get("stocks") or []
            result[offer_id] = sum(s.get("present", 0) for s in stocks)
    return result


async def refresh_snapshot(settings: Settings) -> StockSnapshot:
    """Тянет свежие данные из Ozon + tdcsm.ru, сохраняет снимок, возвращает его.

    Не отправляет в Telegram — это делает независимый ежедневный
    projects/stock-monitor/checker.py (cron на Рег.ру), который эта функция не трогает.
    """
    credentials = _require_credentials(settings)
    ozon_client = OzonSellerClient(credentials, base_url=settings.ozon_api_base_url)
    tdcsm_client = TdcsmClient(base_url=settings.tdcsm_api_base_url)

    offer_ids = await _list_all_offer_ids(ozon_client)
    if not offer_ids:
        return latest_snapshot()

    ozon_stocks = await _stock_for_offer_ids(ozon_client, offer_ids)
    # offer_id всегда совпадает с idcode поставщика в этом проекте (см. checker.py оригинала).
    supplier_data = await tdcsm_client.stock_for_idcodes(offer_ids)

    rows: list[StockRow] = []
    for offer_id in offer_ids:
        ozon_stock = ozon_stocks.get(offer_id, 0)
        supplier_info = supplier_data.get(offer_id)
        supplier_found = supplier_info is not None
        supplier_stock = supplier_info.sellable_stock if supplier_info else None
        name = supplier_info.name if supplier_info else offer_id
        rows.append(
            StockRow(
                offer_id=offer_id,
                name=name,
                ozon_stock=ozon_stock,
                supplier_stock=supplier_stock,
                supplier_found=supplier_found,
                status=classify(ozon_stock, supplier_stock, supplier_found, settings.stock_threshold),
            )
        )

    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    save_snapshot(rows, checked_at)
    return latest_snapshot()


async def apply_stock_to_ozon(settings: Settings) -> StockApplyResult:
    """Проставляет на Ozon остаток поставщика для всех SKU из последнего снимка, где он
    расходится с тем, что сейчас стоит на Ozon. Требует ручного нажатия кнопки —
    ничего не делает само по расписанию (см. README.md оригинального stock-monitor).
    """
    credentials = _require_credentials(settings)
    snapshot = latest_snapshot()
    updates = [
        {
            "offer_id": row.offer_id,
            "stock": row.supplier_stock,
            "warehouse_id": int(settings.stock_warehouse_id),
        }
        for row in snapshot.rows
        if row.supplier_found and row.supplier_stock is not None and row.supplier_stock != row.ozon_stock
    ]
    if not updates:
        return StockApplyResult(updated=0, ok=True, message="Расхождений нет — обновлять нечего.")

    client = OzonSellerClient(credentials, base_url=settings.ozon_api_base_url)
    try:
        await client.set_stocks(updates)
    except Exception as error:  # noqa: BLE001 — отдаём причину на фронт как есть
        return StockApplyResult(updated=0, ok=False, message=f"Ozon отклонил обновление: {error}")
    return StockApplyResult(updated=len(updates), ok=True, message=f"Обновлено SKU: {len(updates)}")
