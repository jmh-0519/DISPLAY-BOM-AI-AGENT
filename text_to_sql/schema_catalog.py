from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from text_to_sql.policy import (
    DEFAULT_TEXT_TO_SQL_POLICY,
    TABLE_DESCRIPTIONS,
    TextToSqlPolicy,
)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    not_null: bool
    primary_key: bool


@dataclass(frozen=True)
class ForeignKeyInfo:
    from_column: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    description: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...]


class SqlSchemaCatalog:
    """Trusted schema introspection for only the Text-to-SQL allowlist."""

    def __init__(
        self,
        database_path: str | Path,
        policy: TextToSqlPolicy = DEFAULT_TEXT_TO_SQL_POLICY,
    ) -> None:
        self.database_path = Path(database_path)
        self.policy = policy

    def load(self) -> tuple[TableInfo, ...]:
        if not self.database_path.exists():
            raise FileNotFoundError(self.database_path)

        connection = sqlite3.connect(str(self.database_path))
        try:
            existing = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = sorted(self.policy.allowed_tables - existing)
            if missing:
                raise RuntimeError(
                    "Text-to-SQL allowlist tables are missing from the database: "
                    + ", ".join(missing)
                )

            tables: list[TableInfo] = []
            for table_name in sorted(self.policy.allowed_tables):
                columns = tuple(
                    ColumnInfo(
                        name=str(row[1]),
                        data_type=str(row[2] or ""),
                        not_null=bool(row[3]),
                        primary_key=bool(row[5]),
                    )
                    for row in connection.execute(
                        f'PRAGMA table_info("{table_name}")'
                    ).fetchall()
                )
                foreign_keys = tuple(
                    ForeignKeyInfo(
                        from_column=str(row[3]),
                        to_table=str(row[2]),
                        to_column=str(row[4]),
                    )
                    for row in connection.execute(
                        f'PRAGMA foreign_key_list("{table_name}")'
                    ).fetchall()
                    if str(row[2]) in self.policy.allowed_tables
                )
                tables.append(
                    TableInfo(
                        name=table_name,
                        description=TABLE_DESCRIPTIONS.get(table_name, ""),
                        columns=columns,
                        foreign_keys=foreign_keys,
                    )
                )
            return tuple(tables)
        finally:
            connection.close()

    def to_prompt_context(self) -> str:
        lines = [
            "SQLite read-only schema available to Text-to-SQL.",
            "Use only the tables and columns listed below.",
            "Do not infer hidden tables or columns.",
        ]
        for table in self.load():
            lines.append(f"\nTABLE {table.name}: {table.description}")
            for column in table.columns:
                flags: list[str] = []
                if column.primary_key:
                    flags.append("PK")
                if column.not_null:
                    flags.append("NOT NULL")
                suffix = f" [{' '.join(flags)}]" if flags else ""
                lines.append(
                    f"  - {column.name}: {column.data_type or 'UNKNOWN'}{suffix}"
                )
            for foreign_key in table.foreign_keys:
                lines.append(
                    "  FK: "
                    f"{table.name}.{foreign_key.from_column} -> "
                    f"{foreign_key.to_table}.{foreign_key.to_column}"
                )
        return "\n".join(lines)
