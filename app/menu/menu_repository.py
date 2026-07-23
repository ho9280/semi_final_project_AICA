"""구조화된 식단 데이터를 SQLite에 저장·조회한다.

표준 라이브러리 ``sqlite3``만 사용하며, 별도 DB 서버 설치가 필요 없다.
같은 (업체, 메뉴종류, 날짜, 식사종류) 조합은 같은 id로 취급해
``INSERT OR REPLACE``로 덮어써서 중복 등록을 방지한다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.menu.config import DB_PATH

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS menu_entries (
    id TEXT PRIMARY KEY,
    organization TEXT NOT NULL,
    menu_type TEXT NOT NULL,
    menu_date TEXT NOT NULL,
    weekday TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    menu_items_json TEXT NOT NULL,
    source_image_path TEXT NOT NULL,
    ocr_raw_text TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def make_entry_id(organization: str, menu_type: str, menu_date: str, meal_type: str) -> str:
    """업체·메뉴종류·날짜·식사종류로 고유 id를 만든다.

    같은 조합으로 다시 등록하면 같은 id가 나와 upsert 시 자동으로 덮어써진다
    (중복 저장 방지).
    """
    return f"{organization}_{menu_type}_{menu_date}_{meal_type}"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "organization": row["organization"],
        "menu_type": row["menu_type"],
        "menu_date": row["menu_date"],
        "weekday": row["weekday"],
        "meal_type": row["meal_type"],
        "menu_items": json.loads(row["menu_items_json"]),
        "source_image_path": row["source_image_path"],
        "ocr_raw_text": row["ocr_raw_text"],
    }


class MenuRepository:
    """식단 데이터 저장소.

    db_path를 지정하지 않으면 config.DB_PATH(data/menu/menu.db)를 사용한다.
    테스트에서는 tmp_path 등으로 별도 경로를 주입해 실제 데이터와 분리한다.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)

    def upsert_menu_entry(self, entry: dict) -> str:
        """구조화된 메뉴 데이터 하나를 저장(또는 갱신)하고 id를 반환한다."""
        entry_id = make_entry_id(
            entry["organization"], entry["menu_type"], entry["menu_date"], entry["meal_type"]
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO menu_entries
                    (id, organization, menu_type, menu_date, weekday, meal_type,
                     menu_items_json, source_image_path, ocr_raw_text, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    organization=excluded.organization,
                    menu_type=excluded.menu_type,
                    menu_date=excluded.menu_date,
                    weekday=excluded.weekday,
                    meal_type=excluded.meal_type,
                    menu_items_json=excluded.menu_items_json,
                    source_image_path=excluded.source_image_path,
                    ocr_raw_text=excluded.ocr_raw_text,
                    updated_at=datetime('now')
                """,
                (
                    entry_id,
                    entry["organization"],
                    entry["menu_type"],
                    entry["menu_date"],
                    entry["weekday"],
                    entry["meal_type"],
                    json.dumps(entry["menu_items"], ensure_ascii=False),
                    entry["source_image_path"],
                    entry.get("ocr_raw_text"),
                ),
            )
        return entry_id

    def get_by_id(self, entry_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM menu_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def get_by_condition(
        self,
        organization: str | None = None,
        menu_date: str | None = None,
        weekday: str | None = None,
        meal_type: str | None = None,
    ) -> list[dict]:
        """업체/날짜/요일/식사종류 조건으로 식단을 조회한다.

        인자를 주지 않으면(None) 해당 조건은 무시된다.
        """
        clauses = []
        params: list[str] = []

        if organization is not None:
            clauses.append("organization = ?")
            params.append(organization)
        if menu_date is not None:
            clauses.append("menu_date = ?")
            params.append(menu_date)
        if weekday is not None:
            clauses.append("weekday = ?")
            params.append(weekday)
        if meal_type is not None:
            clauses.append("meal_type = ?")
            params.append(meal_type)

        query = "SELECT * FROM menu_entries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY menu_date, organization, meal_type"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM menu_entries ORDER BY menu_date, organization, meal_type"
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM menu_entries").fetchone()
        return row["c"]
