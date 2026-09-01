from __future__ import annotations

from core.database_config import sqlite_database_path
from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY
from text_to_sql.schema_catalog import SqlSchemaCatalog


def main() -> None:
    database_path = sqlite_database_path()
    catalog = SqlSchemaCatalog(database_path)
    tables = catalog.load()
    foreign_key_count = sum(len(table.foreign_keys) for table in tables)
    column_count = sum(len(table.columns) for table in tables)

    if len(tables) != len(DEFAULT_TEXT_TO_SQL_POLICY.allowed_tables):
        raise RuntimeError("Text-to-SQL schema catalog table count mismatch")

    print("Text-to-SQL foundation validation passed")
    print(f"- database: {database_path}")
    print(f"- allowed_table_count: {len(tables)}")
    print(f"- allowed_column_count: {column_count}")
    print(f"- allowed_foreign_key_count: {foreign_key_count}")
    print(f"- max_rows: {DEFAULT_TEXT_TO_SQL_POLICY.max_rows}")
    print(f"- timeout_seconds: {DEFAULT_TEXT_TO_SQL_POLICY.timeout_seconds}")
    print("- allowed_tables:")
    for table in tables:
        print(f"  - {table.name}")


if __name__ == "__main__":
    main()
