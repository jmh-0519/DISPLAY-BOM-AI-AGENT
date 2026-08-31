from __future__ import annotations

from pathlib import Path

from database import SQLiteDatabase, SchemaManager
from database.schema import CORE_SCHEMA_VERSION
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
    if not schema or version != CORE_SCHEMA_VERSION:
        raise BomStorageConfigurationError(
            "현재 Clean Core Schema와 호환되는 SQLite DB가 아닙니다."
        )
    if item_count == 0:
        raise BomStorageConfigurationError(
            "SQLite DB에 BOM 기준 데이터가 없습니다. Canonical Seed에서 Runtime DB를 재생성하세요."
        )
    return RepositoryBomService(SQLiteBomRepository(database))
