from __future__ import annotations

from pathlib import Path

from database import SQLiteDatabase, SchemaManager
from repositories import SQLiteBomRepository
from services.repository_bom_service import RepositoryBomService
from core.database_config import sqlite_database_path


class BomStorageConfigurationError(RuntimeError):
    pass


def create_read_bom_service(
    database_path: str | Path | None = None,
):
    """SQLite 전용 조회 Service를 생성합니다."""
    path = Path(database_path or sqlite_database_path())
    if not path.exists():
        raise BomStorageConfigurationError(
            f"SQLite DB를 찾을 수 없습니다: {path}"
        )
    database = SQLiteDatabase(path)
    SchemaManager(database).initialize()
    with database.connection() as connection:
        schema = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='item_master'"
        ).fetchone()
        version = (
            connection.execute(
                "SELECT MAX(version) FROM schema_versions"
            ).fetchone()[0]
            if schema
            else None
        )
        item_count = (
            connection.execute("SELECT COUNT(*) FROM item_master").fetchone()[0]
            if schema
            else 0
        )
    if not schema or version is None or version < 2:
        raise BomStorageConfigurationError(
            "STEP24-A2 v2 Schema가 적용된 SQLite DB가 아닙니다."
        )
    if item_count == 0:
        raise BomStorageConfigurationError(
            "SQLite DB에 이관 데이터가 없습니다. STEP24-B1을 먼저 실행하세요."
        )
    return RepositoryBomService(SQLiteBomRepository(database))
