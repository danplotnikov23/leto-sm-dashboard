"""SQLite-хранилище живой Юнитки — свой файл (unitka_data.db), как и у Остатков,
чтобы не трогать схему основного `leto_bi.db`.

Формульные столбцы никогда не хранятся — только INPUT-поля (`UnitkaRow`) и допущения
(`UnitkaAssumptions`); `UnitkaRowComputed` считается на лету в `unitka_engine.py` при
каждом чтении. Так исключён самый частый риск живых таблиц: формула "протухла" и
показывает старое значение после правки входных данных.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.domain.unitka import UnitkaAssumptions, UnitkaRow

DB_PATH = Path(__file__).resolve().parents[2] / "unitka_data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS unitka_rows (
    id TEXT PRIMARY KEY,
    row_number INTEGER,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unitka_rows_row_number ON unitka_rows(row_number);

CREATE TABLE IF NOT EXISTS unitka_assumptions (
    id TEXT PRIMARY KEY DEFAULT 'default',
    payload TEXT NOT NULL
);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def list_rows() -> list[UnitkaRow]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT payload FROM unitka_rows ORDER BY row_number IS NULL, row_number, id"
    ).fetchall()
    conn.close()
    return [UnitkaRow.model_validate_json(r["payload"]) for r in rows]


def get_row(row_id: str) -> UnitkaRow | None:
    conn = _get_conn()
    row = conn.execute("SELECT payload FROM unitka_rows WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return UnitkaRow.model_validate_json(row["payload"])


def create_row(row: UnitkaRow) -> UnitkaRow:
    if not row.id:
        row = row.model_copy(update={"id": str(uuid4())})
    now = _now()
    conn = _get_conn()
    with conn:
        conn.execute(
            "INSERT INTO unitka_rows (id, row_number, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (row.id, row.row_number, row.model_dump_json(), now, now),
        )
    conn.close()
    return row


def update_row(row_id: str, updated: UnitkaRow) -> UnitkaRow:
    now = _now()
    conn = _get_conn()
    with conn:
        conn.execute(
            "UPDATE unitka_rows SET row_number = ?, payload = ?, updated_at = ? WHERE id = ?",
            (updated.row_number, updated.model_dump_json(), now, row_id),
        )
    conn.close()
    return updated


def delete_row(row_id: str) -> None:
    conn = _get_conn()
    with conn:
        conn.execute("DELETE FROM unitka_rows WHERE id = ?", (row_id,))
    conn.close()


def get_assumptions() -> UnitkaAssumptions:
    conn = _get_conn()
    row = conn.execute(
        "SELECT payload FROM unitka_assumptions WHERE id = 'default'"
    ).fetchone()
    conn.close()
    if row is None:
        return UnitkaAssumptions()
    return UnitkaAssumptions.model_validate_json(row["payload"])


def save_assumptions(assumptions: UnitkaAssumptions) -> UnitkaAssumptions:
    conn = _get_conn()
    with conn:
        conn.execute(
            "INSERT INTO unitka_assumptions (id, payload) VALUES ('default', ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (assumptions.model_dump_json(),),
        )
    conn.close()
    return assumptions


def row_count() -> int:
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) AS c FROM unitka_rows").fetchone()["c"]
    conn.close()
    return int(count)
