"""Публичный API поставщика tdcsm.ru — остатки и публичные цены по idcode.

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
    # `price` — цена продаваемой карточки; `contain` — вложение в логистической
    # упаковке. Умножать их нельзя: 603 ₽ при contain=16 иначе превращаются в 9 648 ₽.
    # purchase_price пока содержит публичную цену до авторизованной сверки.
    price_per_base_unit: float
    purchase_price: float


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
                    product = self._to_stock_info(item)
                    result[product.idcode] = product
        return result

    @staticmethod
    def _to_stock_info(item: dict[str, object]) -> TdcsmStockInfo:
        contain = int(item.get("contain") or 1)
        only_contain_order = bool(item.get("only_contain_order"))
        # tdcsm.ru иногда отдаёт "store": null. Показываем 0, а не выдумываем остаток.
        store_value = item.get("store")
        store = 0 if store_value is None else int(store_value)
        sellable_stock = store // contain if (only_contain_order and contain > 1) else store
        price = float(item.get("price") or 0)
        return TdcsmStockInfo(
            idcode=str(item["idcode"]),
            store=store,
            sellable_stock=sellable_stock,
            contain=contain,
            only_contain_order=only_contain_order,
            price_per_base_unit=price,
            purchase_price=round(price, 2),
            name=html.unescape(str(item.get("name", ""))),
            discontinued=bool(item.get("discontinued", False)),
        )
