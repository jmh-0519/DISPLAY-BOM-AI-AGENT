"""Safe Text-to-SQL foundations for Display BOM AI Agent."""

from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY, TextToSqlPolicy
from text_to_sql.read_only_executor import ReadOnlySqlExecutor, SqlExecutionResult
from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_guard import SqlSafetyError, validate_read_only_sql

__all__ = [
    "DEFAULT_TEXT_TO_SQL_POLICY",
    "ReadOnlySqlExecutor",
    "SqlExecutionResult",
    "SqlSafetyError",
    "SqlSchemaCatalog",
    "TextToSqlPolicy",
    "validate_read_only_sql",
]
