"""Доменные модели мониторинга остатков (перенесено из projects/stock-monitor).

Сверяет остаток уже опубликованных на Ozon товаров с остатком у поставщика
tdcsm.ru. Список офферов не хардкодится — берётся напрямую из Ozon при каждой
проверке. Статусы и пороги — те же, что в исходном `checker.py`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StockStatus(StrEnum):
    OK = "ok"
    CRITICAL = "critical"  # ноль у поставщика
    LOW = "low"  # мало у поставщика (ниже порога)
    MISMATCH = "mismatch"  # на Ozon больше, чем реально есть у поставщика
    RESTOCK = "restock"  # у поставщика снова есть, а на Ozon 0
    UNKNOWN = "unknown"  # не нашли товар у поставщика по этому offer_id


class StockRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str
    name: str
    ozon_stock: int
    supplier_stock: int | None
    supplier_found: bool
    status: StockStatus


class StockCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: int = 0
    critical: int = 0
    low: int = 0
    mismatch: int = 0
    restock: int = 0
    unknown: int = 0


class StockSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked_at: str | None
    total: int
    counts: StockCounts
    diff_count: int
    rows: list[StockRow]


class StockApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated: int
    ok: bool
    message: str
