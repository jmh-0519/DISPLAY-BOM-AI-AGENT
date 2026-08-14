from __future__ import annotations

from pathlib import Path

from database.connection import SQLiteDatabase


class IncompatibleSchemaError(RuntimeError):
    """이전 STEP24 초안 DB가 발견되었을 때 발생합니다."""


class SchemaManager:
    """버전 관리되는 SQL로 빈 SQLite DB를 초기화합니다."""

    DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

    def __init__(self, database: SQLiteDatabase, schema_path: str | Path | None = None) -> None:
        self.database = database
        self.schema_path = Path(schema_path or self.DEFAULT_SCHEMA_PATH)

    def initialize(self) -> None:
        sql = self.schema_path.read_text(encoding="utf-8")
        with self.database.connection() as connection:
            legacy_table = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' "
                "AND name IN ('products','materials','production_bom_items') "
                "LIMIT 1"
            ).fetchone()
            new_table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='item_master'"
            ).fetchone()
            if legacy_table and not new_table:
                raise IncompatibleSchemaError(
                    "이전 STEP24 A2 초안 DB가 발견되었습니다. "
                    "백업이 필요하면 먼저 복사한 뒤 init_database.py의 "
                    "--recreate 옵션으로 새 Schema를 생성하세요."
                )
            connection.executescript(sql)

    def current_version(self) -> int | None:
        with self.database.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_versions'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute("SELECT MAX(version) AS version FROM schema_versions").fetchone()
            return row["version"] if row and row["version"] is not None else None
