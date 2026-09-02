import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from app.domain.models import (
    CompetitorOffer,
    CompetitorSnapshot,
    DataSource,
    PriceImportVersion,
    ShortlistEntry,
    SupplierProduct,
)


def sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        msg = "MVP поддерживает только sqlite:/// database_url"
        raise ValueError(msg)
    path = Path(database_url.removeprefix("sqlite:///")).expanduser()
    if path.is_absolute():
        return path
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / path


class SQLiteStore:
    def __init__(self, database_url: str) -> None:
        self.path = sqlite_path(database_url)
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._connection is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    self._connection = sqlite3.connect(
                        f"{self.path.as_uri()}?mode=rwc",
                        uri=True,
                        check_same_thread=False,
                    )
                except sqlite3.OperationalError as error:
                    msg = (
                        f"Не удалось открыть SQLite-базу: {self.path}. "
                        f"Папка существует: {self.path.parent.exists()}, "
                        f"файл существует: {self.path.exists()}."
                    )
                    raise sqlite3.OperationalError(msg) from error
                self._connection.row_factory = sqlite3.Row
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_versions (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    supplier_name TEXT NOT NULL DEFAULT 'Не указан',
                    imported_at TEXT NOT NULL,
                    total_rows INTEGER NOT NULL,
                    accepted_rows INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    import_version_id TEXT NOT NULL,
                    supplier_name TEXT NOT NULL DEFAULT 'Не указан',
                    supplier_article TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(import_version_id) REFERENCES import_versions(id)
                )
                """
            )
            self._ensure_column(
                connection,
                "import_versions",
                "supplier_name",
                "TEXT NOT NULL DEFAULT 'Не указан'",
            )
            self._ensure_column(
                connection,
                "products",
                "supplier_name",
                "TEXT NOT NULL DEFAULT 'Не указан'",
            )
            self._backfill_supplier_names(connection)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_products_supplier_article "
                "ON products(supplier_name, supplier_article)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS competitor_overrides (
                    supplier_article TEXT PRIMARY KEY,
                    product_id TEXT,
                    title TEXT NOT NULL,
                    price_vat_included REAL NOT NULL,
                    url TEXT NOT NULL,
                    match_type TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(competitor_overrides)").fetchall()
            }
            if "source" not in columns:
                connection.execute(
                    "ALTER TABLE competitor_overrides "
                    "ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shortlist (
                    supplier_name TEXT NOT NULL DEFAULT 'Не указан',
                    supplier_article TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    group_name TEXT NOT NULL DEFAULT '',
                    subgroup_name TEXT NOT NULL DEFAULT '',
                    sale_price_vat_included REAL,
                    planned_sales_qty INTEGER NOT NULL DEFAULT 0,
                    sold_qty INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(supplier_name, supplier_article)
                )
                """
            )
            self._migrate_shortlist_identity(connection)

    def save_import(self, version: PriceImportVersion) -> PriceImportVersion:
        with self.connect() as connection:
            normalized_products: list[SupplierProduct] = []
            for product in version.products:
                existing = connection.execute(
                    "SELECT id FROM products WHERE supplier_name = ? AND supplier_article = ?",
                    (version.supplier_name, product.supplier_article),
                ).fetchone()
                normalized_products.append(
                    product.model_copy(
                        update={
                            "id": str(existing["id"]) if existing is not None else product.id,
                            "supplier_name": version.supplier_name,
                            "source_import_filename": version.filename,
                            "source_imported_at": version.imported_at,
                        }
                    )
                )
            normalized_version = version.model_copy(update={"products": normalized_products})
            payload = normalized_version.model_dump_json()
            connection.execute(
                """
                INSERT INTO import_versions(
                    id, filename, supplier_name, imported_at, total_rows, accepted_rows, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_version.id,
                    normalized_version.filename,
                    normalized_version.supplier_name,
                    normalized_version.imported_at.isoformat(),
                    normalized_version.total_rows,
                    normalized_version.accepted_rows,
                    payload,
                ),
            )
            current_articles = [product.supplier_article for product in normalized_products]
            if current_articles:
                placeholders = ", ".join("?" for _ in current_articles)
                connection.execute(
                    f"DELETE FROM products WHERE supplier_name = ? "
                    f"AND supplier_article NOT IN ({placeholders})",
                    (normalized_version.supplier_name, *current_articles),
                )
            for product in normalized_products:
                connection.execute(
                    """
                    INSERT INTO products(
                        id, import_version_id, supplier_name, supplier_article,
                        title, category, payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(supplier_name, supplier_article) DO UPDATE SET
                        import_version_id = excluded.import_version_id,
                        title = excluded.title,
                        category = excluded.category,
                        payload = excluded.payload
                    """,
                    (
                        product.id,
                        normalized_version.id,
                        normalized_version.supplier_name,
                        product.supplier_article,
                        product.title,
                        product.category,
                        product.model_dump_json(),
                    ),
                )
        return normalized_version

    def list_versions(self) -> list[PriceImportVersion]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM import_versions ORDER BY imported_at DESC"
            ).fetchall()
        return [PriceImportVersion.model_validate(json.loads(row["payload"])) for row in rows]

    def list_products(self) -> list[SupplierProduct]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM products ORDER BY supplier_name, title"
            ).fetchall()
        return [SupplierProduct.model_validate(json.loads(row["payload"])) for row in rows]

    def get_product(self, product_id: str) -> SupplierProduct | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        if row is None:
            return None
        return SupplierProduct.model_validate(json.loads(row["payload"]))

    def get_product_by_supplier_article(
        self,
        supplier_article: str,
        supplier_name: str | None = None,
    ) -> SupplierProduct | None:
        with self.connect() as connection:
            if supplier_name:
                row = connection.execute(
                    "SELECT payload FROM products "
                    "WHERE supplier_article = ? AND supplier_name = ?",
                    (supplier_article, supplier_name),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT products.payload FROM products "
                    "JOIN import_versions ON import_versions.id = products.import_version_id "
                    "WHERE products.supplier_article = ? "
                    "ORDER BY import_versions.imported_at DESC LIMIT 1",
                    (supplier_article,),
                ).fetchone()
        if row is None:
            return None
        return SupplierProduct.model_validate(json.loads(row["payload"]))

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _backfill_supplier_names(connection: sqlite3.Connection) -> None:
        supplier_case = """
            CASE
                WHEN lower(filename) LIKE '%pro-brite%'
                  OR lower(filename) LIKE '%pro brite%' THEN 'Pro-Brite'
                WHEN lower(filename) LIKE '%центр см%'
                  OR lower(filename) LIKE '%price_export%'
                  OR lower(filename) LIKE '%price export%' THEN 'Центр СМ'
                WHEN lower(filename) LIKE '%крепеж%'
                  OR lower(filename) LIKE '%крепёж%' THEN 'ООО КРЕПЕЖ'
                WHEN lower(filename) LIKE '%м8%' THEN 'М8'
                ELSE supplier_name
            END
        """
        connection.execute(
            f"UPDATE import_versions SET supplier_name = {supplier_case} "
            "WHERE supplier_name = 'Не указан'"
        )
        connection.execute(
            """
            UPDATE import_versions
            SET payload = json_set(payload, '$.supplier_name', supplier_name)
            WHERE json_extract(payload, '$.supplier_name') IS NULL
               OR json_extract(payload, '$.supplier_name') = 'Не указан'
            """
        )
        connection.execute(
            """
            UPDATE products
            SET supplier_name = (
                    SELECT supplier_name FROM import_versions
                    WHERE import_versions.id = products.import_version_id
                ),
                payload = json_set(
                    payload,
                    '$.supplier_name',
                    (SELECT supplier_name FROM import_versions
                     WHERE import_versions.id = products.import_version_id),
                    '$.source_import_filename',
                    (SELECT filename FROM import_versions
                     WHERE import_versions.id = products.import_version_id),
                    '$.source_imported_at',
                    (SELECT imported_at FROM import_versions
                     WHERE import_versions.id = products.import_version_id)
                )
            WHERE supplier_name = 'Не указан'
            """
        )

    @staticmethod
    def _migrate_shortlist_identity(connection: sqlite3.Connection) -> None:
        columns = connection.execute("PRAGMA table_info(shortlist)").fetchall()
        primary_key = [
            str(row["name"])
            for row in sorted(columns, key=lambda row: int(row["pk"]))
            if int(row["pk"]) > 0
        ]
        if primary_key == ["supplier_name", "supplier_article"]:
            return
        connection.execute(
            """
            CREATE TABLE shortlist_new (
                supplier_name TEXT NOT NULL DEFAULT 'Не указан',
                supplier_article TEXT NOT NULL,
                product_id TEXT NOT NULL,
                group_name TEXT NOT NULL DEFAULT '',
                subgroup_name TEXT NOT NULL DEFAULT '',
                sale_price_vat_included REAL,
                planned_sales_qty INTEGER NOT NULL DEFAULT 0,
                sold_qty INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(supplier_name, supplier_article)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO shortlist_new(
                supplier_name, supplier_article, product_id, group_name, subgroup_name,
                sale_price_vat_included, planned_sales_qty, sold_qty, note, payload,
                created_at, updated_at
            )
            SELECT
                'Не указан', supplier_article, product_id, group_name, subgroup_name,
                sale_price_vat_included, planned_sales_qty, sold_qty, note,
                json_set(payload, '$.supplier_name', 'Не указан'), created_at, updated_at
            FROM shortlist
            """
        )
        connection.execute("DROP TABLE shortlist")
        connection.execute("ALTER TABLE shortlist_new RENAME TO shortlist")

    def get_product_import_source(self, product_id: str) -> tuple[str, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT import_versions.filename, import_versions.imported_at
                FROM products
                JOIN import_versions ON import_versions.id = products.import_version_id
                WHERE products.id = ?
                """,
                (product_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["filename"]), str(row["imported_at"])

    def list_shortlist_entries(self) -> list[ShortlistEntry]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM shortlist ORDER BY updated_at DESC"
            ).fetchall()
        return [ShortlistEntry.model_validate(json.loads(row["payload"])) for row in rows]

    def get_shortlist_entry(
        self,
        supplier_article: str,
        supplier_name: str | None = None,
    ) -> ShortlistEntry | None:
        with self.connect() as connection:
            if supplier_name:
                row = connection.execute(
                    "SELECT payload FROM shortlist "
                    "WHERE supplier_article = ? AND supplier_name = ?",
                    (supplier_article, supplier_name),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload FROM shortlist WHERE supplier_article = ? "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (supplier_article,),
                ).fetchone()
        if row is None:
            return None
        return ShortlistEntry.model_validate(json.loads(row["payload"]))

    def get_shortlist_entry_by_product_id(self, product_id: str) -> ShortlistEntry | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM shortlist WHERE product_id = ?",
                (product_id,),
            ).fetchone()
        if row is None:
            return None
        return ShortlistEntry.model_validate(json.loads(row["payload"]))

    def save_shortlist_entry(self, entry: ShortlistEntry) -> ShortlistEntry:
        normalized = entry.model_copy(
            update={
                "group_name": entry.group_name.strip(),
                "subgroup_name": entry.subgroup_name.strip(),
                "purchase_price_vat_included": self._positive_or_none(
                    entry.purchase_price_vat_included
                ),
                "length_cm": self._positive_or_none(entry.length_cm),
                "width_cm": self._positive_or_none(entry.width_cm),
                "height_cm": self._positive_or_none(entry.height_cm),
                "seller_bonus_percent": self._percent_or_none(entry.seller_bonus_percent),
                "advertising_drr_percent": self._percent_or_none(
                    entry.advertising_drr_percent
                ),
                "offer_quantity": max(int(entry.offer_quantity), 1),
                "planned_sales_qty": max(int(entry.planned_sales_qty), 0),
                "sold_qty": max(int(entry.sold_qty), 0),
                "note": entry.note.strip(),
            }
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shortlist(
                    supplier_name,
                    supplier_article,
                    product_id,
                    group_name,
                    subgroup_name,
                    sale_price_vat_included,
                    planned_sales_qty,
                    sold_qty,
                    note,
                    payload,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(supplier_name, supplier_article) DO UPDATE SET
                    product_id = excluded.product_id,
                    group_name = excluded.group_name,
                    subgroup_name = excluded.subgroup_name,
                    sale_price_vat_included = excluded.sale_price_vat_included,
                    planned_sales_qty = excluded.planned_sales_qty,
                    sold_qty = excluded.sold_qty,
                    note = excluded.note,
                    payload = excluded.payload,
                    updated_at = datetime('now')
                """,
                (
                    normalized.supplier_name,
                    normalized.supplier_article,
                    normalized.product_id,
                    normalized.group_name,
                    normalized.subgroup_name,
                    normalized.sale_price_vat_included,
                    normalized.planned_sales_qty,
                    normalized.sold_qty,
                    normalized.note,
                    normalized.model_dump_json(),
                ),
            )
        return normalized

    def delete_shortlist_entry(
        self,
        supplier_article: str,
        supplier_name: str | None = None,
    ) -> None:
        with self.connect() as connection:
            if supplier_name:
                connection.execute(
                    "DELETE FROM shortlist WHERE supplier_article = ? AND supplier_name = ?",
                    (supplier_article, supplier_name),
                )
            else:
                connection.execute(
                    "DELETE FROM shortlist WHERE supplier_article = ?",
                    (supplier_article,),
                )

    def delete_shortlist_entry_by_product_id(self, product_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM shortlist WHERE product_id = ?",
                (product_id,),
            )

    def save_competitor_override(
        self,
        product: SupplierProduct,
        offer: CompetitorOffer,
    ) -> CompetitorSnapshot:
        return self.save_competitor_offer(product, offer, DataSource.MANUAL)

    def save_competitor_offer(
        self,
        product: SupplierProduct,
        offer: CompetitorOffer,
        source: DataSource,
    ) -> CompetitorSnapshot:
        normalized_offer = offer.model_copy(update={"source": source})
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO competitor_overrides(
                    supplier_article,
                    product_id,
                    title,
                    price_vat_included,
                    url,
                    match_type,
                    source,
                    payload,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    product.supplier_article,
                    product.id,
                    normalized_offer.title,
                    normalized_offer.price_vat_included,
                    normalized_offer.url or "",
                    normalized_offer.match_type,
                    source,
                    normalized_offer.model_dump_json(),
                ),
            )
        return self.get_competitor_snapshot(product)

    def get_competitor_snapshot(self, product: SupplierProduct) -> CompetitorSnapshot:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT payload, source
                FROM competitor_overrides
                WHERE supplier_article = ?
                """,
                (product.supplier_article,),
            ).fetchone()
        if row is None:
            return CompetitorSnapshot(product_id=product.id, offers=[], source=DataSource.MISSING)
        source = self._data_source(row["source"])
        offer = CompetitorOffer.model_validate(json.loads(row["payload"])).model_copy(
            update={"source": source}
        )
        return CompetitorSnapshot(
            product_id=product.id,
            offers=[offer],
            source=source,
        )

    def _data_source(self, value: object) -> DataSource:
        try:
            return DataSource(str(value))
        except ValueError:
            return DataSource.MANUAL

    def _positive_or_none(self, value: float | None) -> float | None:
        if value is None:
            return None
        return value if value > 0 else None

    def _percent_or_none(self, value: float | None) -> float | None:
        if value is None:
            return None
        return max(float(value), 0.0)
