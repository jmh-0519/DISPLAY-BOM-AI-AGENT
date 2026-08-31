from __future__ import annotations

from pathlib import Path

from database.connection import SQLiteDatabase


REMOVED_LEGACY_TABLES = (
    "bom_review_checks",
    "bom_reviews",
    "review_bom_items",
    "review_bom_revisions",
    "production_apply_history",
    "workflow_events",
    "review_boms",
    "design_change_snapshot_items",
    "design_change_snapshots",
    "design_change_checks",
    "design_change_items",
    "design_changes",
    "review_checklists",
    "legacy_change_history",
    "material_attributes",
    "material_compatibility",
    "design_rules",
)


class IncompatibleSchemaError(RuntimeError):
    """이전 STEP24 초안 DB가 발견되었을 때 발생합니다."""


class SchemaManager:
    """버전 관리되는 SQL로 빈 SQLite DB를 초기화합니다."""

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
    def _columns(connection, table_name: str) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(f'PRAGMA table_info("{table_name}")')
        }

    def _prepare_v4_columns(self, connection) -> None:
        """Make an existing v3 DB executable by the v4 idempotent schema SQL."""
        if self._table_exists(connection, "plants"):
            if "country_code" not in self._columns(connection, "plants"):
                connection.execute(
                    "ALTER TABLE plants ADD COLUMN country_code TEXT NOT NULL DEFAULT 'KR'"
                )

        plant_tables = (
            "bom_master",
            "change_requests",
            "change_actions",
            "candidate_evaluations",
            "change_impacts",
            "change_previews",
            "change_apply_results",
        )
        for table_name in plant_tables:
            if (
                self._table_exists(connection, table_name)
                and "plant_code" not in self._columns(connection, table_name)
            ):
                connection.execute(
                    f'ALTER TABLE "{table_name}" '
                    "ADD COLUMN plant_code TEXT NOT NULL DEFAULT 'P01'"
                )


    @staticmethod
    def _remove_legacy_tables_v7(connection) -> None:
        """Remove superseded workflow/review schema before applying Clean Core SQL."""
        for table_name in REMOVED_LEGACY_TABLES:
            connection.execute(f'DROP TABLE IF EXISTS "{table_name}"')

    def _prepare_v6_columns(self, connection) -> None:
        """Add STEP32 explainability columns to an existing Phase3 database."""
        if not self._table_exists(connection, "candidate_evaluations"):
            return
        columns = self._columns(connection, "candidate_evaluations")
        additions = {
            "supplier_evaluation_json": "TEXT NOT NULL DEFAULT '{}'",
            "demand_context_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f'ALTER TABLE "candidate_evaluations" ADD COLUMN {name} {definition}'
                )

    @staticmethod
    def _rebuild_bom_master_v4(connection) -> None:
        """Upgrade the core BOM key so the same relation can exist per Plant."""
        connection.execute("DROP INDEX IF EXISTS ix_bom_parent_dates")
        connection.execute("DROP INDEX IF EXISTS ix_bom_child_dates")
        connection.execute("DROP INDEX IF EXISTS ix_bom_parent_sequence")
        connection.execute("ALTER TABLE bom_master RENAME TO bom_master_v3")
        connection.execute(
            """
            CREATE TABLE bom_master (
              bom_id INTEGER PRIMARY KEY AUTOINCREMENT,
              plant_code TEXT NOT NULL,
              parent_item_code TEXT NOT NULL,
              child_item_code TEXT NOT NULL,
              location_code TEXT NOT NULL DEFAULT 'N/A',
              sequence_no INTEGER NOT NULL DEFAULT 0 CHECK(sequence_no >= 0),
              quantity REAL NOT NULL CHECK(quantity > 0),
              valid_from TEXT NOT NULL,
              valid_to TEXT,
              row_revision INTEGER NOT NULL DEFAULT 1 CHECK(row_revision >= 1),
              status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('DRAFT','ACTIVE','INACTIVE')),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(plant_code) REFERENCES plants(plant_code),
              FOREIGN KEY(parent_item_code) REFERENCES item_master(item_code),
              FOREIGN KEY(child_item_code) REFERENCES item_master(item_code),
              FOREIGN KEY(location_code) REFERENCES location_master(location_code),
              CHECK(parent_item_code <> child_item_code),
              CHECK(valid_to IS NULL OR valid_to >= valid_from),
              UNIQUE(plant_code,parent_item_code,child_item_code,location_code,valid_from)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO bom_master(
              bom_id,plant_code,parent_item_code,child_item_code,location_code,
              sequence_no,quantity,valid_from,valid_to,row_revision,status,
              created_at,updated_at
            )
            SELECT bom_id,COALESCE(plant_code,'P01'),parent_item_code,child_item_code,
                   location_code,sequence_no,quantity,valid_from,valid_to,row_revision,
                   status,created_at,updated_at
            FROM bom_master_v3
            """
        )
        connection.execute("DROP TABLE bom_master_v3")
        connection.execute(
            "CREATE INDEX ix_bom_parent_dates ON "
            "bom_master(plant_code,parent_item_code,status,valid_from,valid_to)"
        )
        connection.execute(
            "CREATE INDEX ix_bom_child_dates ON "
            "bom_master(plant_code,child_item_code,status,valid_from,valid_to)"
        )
        connection.execute(
            "CREATE INDEX ix_bom_parent_sequence ON "
            "bom_master(plant_code,parent_item_code,sequence_no)"
        )

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
            version_before = None
            if self._table_exists(connection, "schema_versions"):
                row = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_versions"
                ).fetchone()
                version_before = row["version"] if row else None
            upgrading_to_v4 = bool(new_table and (version_before or 0) < 4)
            upgrading_to_v6 = bool(new_table and (version_before or 0) < 6)
            upgrading_to_v7 = bool(new_table and (version_before or 0) < 7)
            if upgrading_to_v4:
                self._prepare_v4_columns(connection)
            if upgrading_to_v6:
                self._prepare_v6_columns(connection)
            if upgrading_to_v7:
                self._remove_legacy_tables_v7(connection)
            connection.executescript(sql)
            if upgrading_to_v4:
                connection.execute("PRAGMA foreign_keys = OFF")
                self._rebuild_bom_master_v4(connection)
                connection.commit()
                connection.execute("PRAGMA foreign_keys = ON")

    def current_version(self) -> int | None:
        with self.database.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_versions'"
            ).fetchone()
            if not exists:
                return None
            row = connection.execute("SELECT MAX(version) AS version FROM schema_versions").fetchone()
            return row["version"] if row and row["version"] is not None else None
