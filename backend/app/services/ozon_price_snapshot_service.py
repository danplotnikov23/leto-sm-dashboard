import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from app.core.config import Settings
from app.schemas.ozon_price import OzonPriceSnapshot
from app.services.ozon_seller_client import OzonSellerClient


class OzonPriceSnapshotService:
    def __init__(self, settings: Settings) -> None:
        self._database_path = settings.database_path
        self._seller_client = OzonSellerClient(settings)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    async def fetch_current_snapshots(
        self,
        offer_ids: list[str],
    ) -> list[OzonPriceSnapshot]:
        normalized_offer_ids = [
            offer_id.strip()
            for offer_id in offer_ids
            if offer_id and offer_id.strip()
        ]
        if not normalized_offer_ids:
            return []

        products_by_offer_id, prices_by_offer_id = await asyncio.gather(
            self._seller_client.get_products_by_offer_id(normalized_offer_ids),
            self._seller_client.get_product_prices_by_offer_id(normalized_offer_ids),
        )
        fetched_at = datetime.now(UTC).isoformat()
        snapshots = [
            _build_snapshot(
                offer_id,
                products_by_offer_id.get(offer_id, {}),
                prices_by_offer_id.get(offer_id, {}),
                fetched_at,
            )
            for offer_id in normalized_offer_ids
            if offer_id in prices_by_offer_id or offer_id in products_by_offer_id
        ]
        await asyncio.to_thread(self._save_snapshots, snapshots)
        return snapshots

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ozon_price_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offer_id TEXT NOT NULL,
                    product_id TEXT,
                    sku TEXT,
                    title TEXT,
                    fetched_at TEXT NOT NULL,
                    price_with_vat REAL,
                    old_price_with_vat REAL,
                    min_price_with_vat REAL,
                    marketing_seller_price_with_vat REAL,
                    net_price REAL,
                    vat REAL,
                    source TEXT NOT NULL,
                    raw_price_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ozon_price_snapshots_offer_date
                    ON ozon_price_snapshots (offer_id, fetched_at)
                """
            )

    def _save_snapshots(self, snapshots: list[OzonPriceSnapshot]) -> None:
        if not snapshots:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO ozon_price_snapshots (
                    offer_id,
                    product_id,
                    sku,
                    title,
                    fetched_at,
                    price_with_vat,
                    old_price_with_vat,
                    min_price_with_vat,
                    marketing_seller_price_with_vat,
                    net_price,
                    vat,
                    source,
                    raw_price_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot.offer_id,
                        snapshot.product_id,
                        snapshot.sku,
                        snapshot.title,
                        snapshot.fetched_at,
                        snapshot.price_with_vat,
                        snapshot.old_price_with_vat,
                        snapshot.min_price_with_vat,
                        snapshot.marketing_seller_price_with_vat,
                        snapshot.net_price,
                        snapshot.vat,
                        snapshot.source,
                        json.dumps(snapshot.raw_price, ensure_ascii=False),
                    )
                    for snapshot in snapshots
                ],
            )


def _build_snapshot(
    offer_id: str,
    product: dict[str, object],
    price_item: dict[str, object],
    fetched_at: str,
) -> OzonPriceSnapshot:
    price = price_item.get("price")
    raw_price = price if isinstance(price, dict) else {}
    return OzonPriceSnapshot(
        offer_id=offer_id,
        product_id=_optional_text(
            price_item.get("product_id")
            or product.get("id")
            or product.get("product_id")
        ),
        sku=_optional_text(product.get("sku")),
        title=_optional_text(product.get("name")),
        fetched_at=fetched_at,
        price_with_vat=_optional_float(raw_price.get("price") or product.get("price")),
        old_price_with_vat=_optional_float(
            raw_price.get("old_price") or product.get("old_price")
        ),
        min_price_with_vat=_optional_float(
            raw_price.get("min_price") or product.get("min_price")
        ),
        marketing_seller_price_with_vat=_optional_float(
            raw_price.get("marketing_seller_price")
        ),
        net_price=_optional_float(raw_price.get("net_price")),
        vat=_optional_float(raw_price.get("vat") or product.get("vat")),
        raw_price=raw_price,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, int | float):
        return float(value)

    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None
