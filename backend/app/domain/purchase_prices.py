"""Контракт сверки закупочных цен опубликованных SKU.

Снимок намеренно не хранится в SQLite: цена поставщика и набор опубликованных
офферов меняются вне платформы. Каждое обновление запрашивает оба источника
заново, а действие "Применить" повторяет сверку перед записью в живую юнитку.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PurchasePriceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    supplier_name: str | None
    unitka_row_id: str | None
    unitka_title: str | None
    current_purchase_price: float | None
    supplier_purchase_price: float | None
    delta: float | None
    supplier_found: bool
    in_unitka: bool


class PurchasePriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked_at: str
    total_published: int
    matched_to_unitka: int
    supplier_not_found: int
    diff_count: int
    rows: list[PurchasePriceRow]


class PurchasePriceApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated: int
    ok: bool
    message: str
