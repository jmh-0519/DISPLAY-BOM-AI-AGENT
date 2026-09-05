from __future__ import annotations

from pathlib import Path

from database.connection import SQLiteDatabase


CORE_SCHEMA_VERSION = 9
CORE_SCHEMA_TABLES = frozenset({
    "assembly_master",
    "bom_hierarchy_rules",
    "bom_master",
    "candidate_evaluations",
    "candidate_rule_results",
    "change_action_reasons",
    "change_actions",
    "change_apply_results",
    "change_approvals",
    "change_impacts",
    "change_previews",
    "change_reason_alias",
    "change_reason_master",
    "change_reason_scope",
    "change_requests",
    "dataset_exports",
    "inventory_balances",
    "inventory_locations",
    "item_attribute_values",
    "item_master",
    "location_master",
    "material_master",
    "performance_outcomes",
    "plants",
    "production_plans",
    "query_aliases",
    "rule_conditions",
    "rule_definitions",
    "rule_revisions",
    "schema_versions",
    "substitution_relations",
    "supplier_items",
    "supplier_master",
    "version_master",
    "warehouses",
})


class IncompatibleSchemaError(RuntimeError):
    """현재 Display BOM 스키마와 호환되지 않는 SQLite Schema입니다."""


class SchemaManager:
    """현재 Display BOM SQL Schema를 초기화하고 검증합니다."""

    DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

    def __init__(self, database: SQLiteDatabase, schema_path: str | Path | None = None) -> None:
        self.database = database
        self.schema_path = Path(schema_path or self.DEFAULT_SCHEMA_PATH)

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone() is not None

    @staticmethod
    def _user_tables(connection) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @classmethod
    def _validate_current_schema(cls, connection) -> None:
        tables = cls._user_tables(connection)
        missing = sorted(CORE_SCHEMA_TABLES - tables)
        unexpected = sorted(tables - CORE_SCHEMA_TABLES)
        if missing or unexpected:
            raise IncompatibleSchemaError(
                "Display BOM DB Schema가 현재 기준과 일치하지 않습니다. "
                f"missing={missing}, unexpected={unexpected}. "
                "Canonical Seed DB에서 재생성하세요."
            )

    def initialize(self) -> None:
        sql = self.schema_path.read_text(encoding="utf-8")
        with self.database.connection() as connection:
            has_current_core = self._table_exists(connection, "item_master")
            if has_current_core and self._table_exists(connection, "schema_versions"):
                row = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_versions"
                ).fetchone()
                version = row["version"] if row else None
                if (version or 0) < CORE_SCHEMA_VERSION:
                    raise IncompatibleSchemaError(
                        "현재 지원 버전보다 이전 DB Schema입니다. "
                        "Canonical Seed DB에서 재생성하거나 init_database.py의 "
                        "--recreate 옵션을 사용하세요."
                    )
            elif self._user_tables(connection):
                raise IncompatibleSchemaError(
                    "현재 Release와 호환되지 않는 기존 DB Schema입니다. "
                    "백업이 필요하면 먼저 복사한 뒤 init_database.py의 "
                    "--recreate 옵션을 사용하세요."
                )

            connection.executescript(sql)
            self._validate_current_schema(connection)

    def current_version(self) -> int | None:
        with self.database.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_versions'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_versions"
            ).fetchone()
            return row["version"] if row and row["version"] is not None else None
