"""Публичный API поставщика tdcsm.ru — остатки по idcode (без логина).

Перенос 1:1 из `projects/stock-monitor/apis.py::tdcsm_stock_for_idcodes` (тот же
рабочий код, что уже используется в ежедневном Telegram-боте «Остатки Лето СМ»),
только на httpx/async вместо urllib — чтобы не заводить вторую HTTP-библиотеку
в проекте. Логика пересчёта остатка не менялась ни на йоту.
"""

from __future__ import annotations

import html

import httpx
from pydantic import BaseModel


class TdcsmStockInfo(BaseModel):
    idcode: str
    store: int
    sellable_stock: int
    contain: int
    only_contain_order: bool
    name: str
    discontinued: bool


class TdcsmClient:
    def __init__(self, base_url: str = "https://tdcsm.ru", timeout: float = 30.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    async def stock_for_idcodes(self, idcodes: list[str]) -> dict[str, TdcsmStockInfo]:
        """idcode -> остаток. "store" у поставщика — количество БАЗОВЫХ единиц (например,
        отдельных саморезов), а не количество продаваемых на Ozon упаковок. Когда
        only_contain_order=true, товар продаётся только целыми упаковками по "contain"
        штук — тогда реальный остаток в упаковках = store // contain.

        Баг, который эта логика чинит (найден 2026-08-27 в исходном stock-monitor):
        Саморез Torx 10765398 — store=22500 (шт), contain=500 (шт/упаковка),
        only_contain_order=true -> реально 45 упаковок, не 22500. Сервис до фикса
        проставлял на Ozon 22500 и товар продавался бы "в минус".
        """
        result: dict[str, TdcsmStockInfo] = {}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for i in range(0, len(idcodes), 100):
                chunk = idcodes[i : i + 100]
                response = await client.post(
                    "/api/ecm/tdcsm/products/idcodes/",
                    json=chunk,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; leto-sm-platform/1.0)"},
                )
                response.raise_for_status()
                for item in response.json():
                    contain = item.get("contain") or 1
                    only_contain_order = bool(item.get("only_contain_order"))
                    # tdcsm.ru иногда отдаёт "store": null (не отсутствие поля, а явный null —
                    # .get(key, 0) в этом случае вернул бы None, не 0) для товаров без учёта
                    # остатка на их стороне. Трактуем как 0 — это безопасное направление
                    # ошибки (лучше ложно показать "нет в наличии", чем скрыть реальный ноль).
                    store = item.get("store")
                    store = 0 if store is None else store
                    sellable_stock = (
                        store // contain if (only_contain_order and contain > 1) else store
                    )
                    result[item["idcode"]] = TdcsmStockInfo(
                        idcode=item["idcode"],
                        store=store,
                        sellable_stock=sellable_stock,
                        contain=contain,
                        only_contain_order=only_contain_order,
                        # tdcsm.ru отдаёт название с HTML-сущностями (например "&#215;" вместо
                        # "×") — их декодирует Telegram (parse_mode=HTML в checker.py), но не
                        # декодирует обычный текстовый рендер в браузере, поэтому распаковываем
                        # здесь, один раз, для всех потребителей этого клиента.
                        name=html.unescape(item.get("name", "")),
                        discontinued=item.get("discontinued", False),
                    )
        return result
