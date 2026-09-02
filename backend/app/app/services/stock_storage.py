"""SQLite-хранилище снимков остатков — перенос `projects/stock-monitor/storage.py`.

Отдельный файл базы (не `leto_bi.db`), чтобы не трогать схему и миграции основного
хранилища (`app/db/sqlite.py`) ради независимого небольшого модуля.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.domain.stock import StockCounts, StockRow, StockSnapshot, StockStatus

DB_PATH = Path(__file__).resolve().parents[2] / "stock_data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    ozon_stock INTEGER NOT NULL,
    supplier_stock INTEGER,
    supplier_found INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stock_snapshots_checked_at ON stock_snapshots(checked_at);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_snapshot(rows: list[StockRow], checked_at: str) -> None:
    conn = _get_conn()
    with conn:
        conn.executemany(
            """INSERT INTO stock_snapshots
               (checked_at, offer_id, name, ozon_stock, supplier_stock, supplier_found, status)
               VALUES (:checked_at, :offer_id, :name, :ozon_stock, :supplier_stock,
                       :supplier_found, :status)""",
            [
                {
                    "checked_at": checked_at,
                    "offer_id": r.offer_id,
                    "name": r.name,
                    "ozon_stock": r.ozon_stock,
                    "supplier_stock": r.supplier_stock,
                    "supplier_found": int(r.supplier_found),
                    "status": r.status.value,
                }
                for r in rows
            ],
        )
    conn.close()


_STATUS_ORDER = {
    StockStatus.CRITICAL: 0,
    StockStatus.LOW: 1,
    StockStatus.MISMATCH: 2,
    StockStatus.RESTOCK: 3,
    StockStatus.UNKNOWN: 4,
    StockStatus.OK: 5,
}


def latest_snapshot() -> StockSnapshot:
    conn = _get_conn()
    latest_ts = conn.execute("SELECT MAX(checked_at) AS m FROM stock_snapshots").fetchone()["m"]
    if not latest_ts:
        conn.close()
        return StockSnapshot(checked_at=None, total=0, counts=StockCounts(), diff_count=0, rows=[])

    db_rows = conn.execute(
        "SELECT * FROM stock_snapshots WHERE checked_at = ?",
        (latest_ts,),
    ).fetchall()
    conn.close()

    rows = [
        StockRow(
            offer_id=r["offer_id"],
            name=r["name"],
            ozon_stock=r["ozon_stock"],
            supplier_stock=r["supplier_stock"],
            supplier_found=bool(r["supplier_found"]),
            status=StockStatus(r["status"]),
        )
        for r in db_rows
    ]
    rows.sort(key=lambda r: _STATUS_ORDER.get(r.status, 9))

    counts = StockCounts()
    for r in rows:
        setattr(counts, r.status.value, getattr(counts, r.status.value) + 1)

    diff_count = sum(
        1
        for r in rows
        if r.supplier_found and r.supplier_stock is not None and r.supplier_stock != r.ozon_stock
    )

    return StockSnapshot(
        checked_at=latest_ts,
        total=len(rows),
        counts=counts,
        diff_count=diff_count,
        rows=rows,
    )
