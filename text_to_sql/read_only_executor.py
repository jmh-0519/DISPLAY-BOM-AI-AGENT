from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY, TextToSqlPolicy
from text_to_sql.sql_guard import SqlSafetyError, validate_read_only_sql


@dataclass(frozen=True)
class SqlExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int
    truncated: bool
    elapsed_ms: float


class ReadOnlySqlExecutor:
    """Execute validated SQL under multiple independent SQLite safety layers."""

    def __init__(
        self,
        database_path: str | Path,
        policy: TextToSqlPolicy = DEFAULT_TEXT_TO_SQL_POLICY,
    ) -> None:
        self.database_path = Path(database_path)
        self.policy = policy

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.exists():
            raise FileNotFoundError(self.database_path)
        resolved = self.database_path.resolve().as_posix()
        connection = sqlite3.connect(
            f"file:{resolved}?mode=ro",
            uri=True,
            timeout=max(0.1, self.policy.timeout_seconds),
        )
        connection.row_factory = sqlite3.Row
        # Defense in depth: OS/file URI read-only + SQLite query_only + authorizer.
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _authorizer(self):
        allowed_tables = self.policy.allowed_tables
        allowed_functions = self.policy.allowed_functions

        allowed_actions = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
        }
        recursive = getattr(sqlite3, "SQLITE_RECURSIVE", None)
        if recursive is not None:
            allowed_actions.add(recursive)

        def authorize(action: int, arg1: str | None, arg2: str | None, db: str | None, trigger: str | None) -> int:
            del db, trigger
            if action not in allowed_actions:
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_READ:
                table = str(arg1 or "")
                if table not in allowed_tables:
                    return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                # CPython/SQLite normally exposes the function name in arg2.
                function_name = str(arg2 or arg1 or "").strip().lower()
                if function_name not in allowed_functions:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        return authorize

    def execute(self, sql: str) -> SqlExecutionResult:
        validate_read_only_sql(sql, self.policy)
        connection = self._connect()
        started = time.monotonic()
        deadline = started + self.policy.timeout_seconds
        try:
            connection.set_authorizer(self._authorizer())

            def progress_handler() -> int:
                return 1 if time.monotonic() > deadline else 0

            connection.set_progress_handler(
                progress_handler,
                self.policy.progress_check_opcodes,
            )
            try:
                cursor = connection.execute(sql)
                columns = tuple(
                    str(description[0]) for description in (cursor.description or ())
                )
                raw_rows = cursor.fetchmany(self.policy.max_rows + 1)
            except sqlite3.DatabaseError as error:
                message = str(error)
                if ("not authorized" in message.lower() or "prohibited" in message.lower()):
                    raise SqlSafetyError(
                        "SQL was blocked by the read-only SQLite authorizer"
                    ) from error
                if "interrupted" in message.lower():
                    raise SqlSafetyError(
                        f"SQL exceeded timeout_seconds={self.policy.timeout_seconds}"
                    ) from error
                raise

            truncated = len(raw_rows) > self.policy.max_rows
            raw_rows = raw_rows[: self.policy.max_rows]
            rows = tuple({column: row[column] for column in columns} for row in raw_rows)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            return SqlExecutionResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        finally:
            connection.close()
