from __future__ import annotations

import re
from dataclasses import dataclass

from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY, TextToSqlPolicy


class SqlSafetyError(ValueError):
    """Raised when a candidate SQL statement violates Text-to-SQL policy."""


@dataclass(frozen=True)
class ValidatedSql:
    sql: str
    statement_kind: str


def _sanitize_for_structure(sql: str) -> str:
    """Remove SQL comments while preserving quoted strings/identifiers.

    This helper is intentionally not a full SQL parser. Runtime authority is the
    SQLite read-only connection plus authorizer. The scanner exists only to make
    obvious invalid/multi-statement input fail early and clearly.
    """
    result: list[str] = []
    i = 0
    state = "NORMAL"
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state == "NORMAL":
            if ch == "'":
                state = "SINGLE"
                result.append(ch)
            elif ch == '"':
                state = "DOUBLE"
                result.append(ch)
            elif ch == "`":
                state = "BACKTICK"
                result.append(ch)
            elif ch == "[":
                state = "BRACKET"
                result.append(ch)
            elif ch == "-" and nxt == "-":
                state = "LINE_COMMENT"
                result.extend("  ")
                i += 1
            elif ch == "/" and nxt == "*":
                state = "BLOCK_COMMENT"
                result.extend("  ")
                i += 1
            else:
                result.append(ch)
        elif state == "SINGLE":
            result.append(ch)
            if ch == "'":
                if nxt == "'":
                    result.append(nxt)
                    i += 1
                else:
                    state = "NORMAL"
        elif state == "DOUBLE":
            result.append(ch)
            if ch == '"':
                if nxt == '"':
                    result.append(nxt)
                    i += 1
                else:
                    state = "NORMAL"
        elif state == "BACKTICK":
            result.append(ch)
            if ch == "`":
                state = "NORMAL"
        elif state == "BRACKET":
            result.append(ch)
            if ch == "]":
                state = "NORMAL"
        elif state == "LINE_COMMENT":
            if ch in "\r\n":
                state = "NORMAL"
                result.append(ch)
            else:
                result.append(" ")
        elif state == "BLOCK_COMMENT":
            if ch == "*" and nxt == "/":
                result.extend("  ")
                i += 1
                state = "NORMAL"
            else:
                result.append(" ")
        i += 1

    if state in {"SINGLE", "DOUBLE", "BACKTICK", "BRACKET", "BLOCK_COMMENT"}:
        raise SqlSafetyError("SQL contains an unterminated quoted value, identifier or comment")
    return "".join(result)


def _semicolon_positions(sql: str) -> list[int]:
    positions: list[int] = []
    i = 0
    state = "NORMAL"
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if state == "NORMAL":
            if ch == "'":
                state = "SINGLE"
            elif ch == '"':
                state = "DOUBLE"
            elif ch == "`":
                state = "BACKTICK"
            elif ch == "[":
                state = "BRACKET"
            elif ch == "-" and nxt == "-":
                state = "LINE_COMMENT"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "BLOCK_COMMENT"
                i += 1
            elif ch == ";":
                positions.append(i)
        elif state == "SINGLE" and ch == "'":
            if nxt == "'":
                i += 1
            else:
                state = "NORMAL"
        elif state == "DOUBLE" and ch == '"':
            if nxt == '"':
                i += 1
            else:
                state = "NORMAL"
        elif state == "BACKTICK" and ch == "`":
            state = "NORMAL"
        elif state == "BRACKET" and ch == "]":
            state = "NORMAL"
        elif state == "LINE_COMMENT" and ch in "\r\n":
            state = "NORMAL"
        elif state == "BLOCK_COMMENT" and ch == "*" and nxt == "/":
            state = "NORMAL"
            i += 1
        i += 1
    return positions


def validate_read_only_sql(
    sql: str,
    policy: TextToSqlPolicy = DEFAULT_TEXT_TO_SQL_POLICY,
) -> ValidatedSql:
    if not isinstance(sql, str) or not sql.strip():
        raise SqlSafetyError("SQL must be a non-empty string")
    if "\x00" in sql:
        raise SqlSafetyError("SQL contains a NUL byte")
    if len(sql) > policy.max_sql_length:
        raise SqlSafetyError(
            f"SQL exceeds max_sql_length={policy.max_sql_length}"
        )

    sanitized = _sanitize_for_structure(sql).strip()
    if not sanitized:
        raise SqlSafetyError("SQL contains no executable statement")

    semicolons = _semicolon_positions(sql)
    if len(semicolons) > 1:
        raise SqlSafetyError("Multiple SQL statements are not allowed")
    if len(semicolons) == 1:
        # The only semicolon may terminate the single statement. Comments and
        # whitespace after it are ignored by _sanitize_for_structure.
        sanitized_no_comments = sanitized.rstrip()
        if not sanitized_no_comments.endswith(";"):
            raise SqlSafetyError("Multiple SQL statements are not allowed")
        sanitized = sanitized_no_comments[:-1].rstrip()

    first_match = re.match(r"(?is)^\s*([A-Z_]+)\b", sanitized)
    first = first_match.group(1).upper() if first_match else ""
    if first not in {"SELECT", "WITH"}:
        raise SqlSafetyError(
            "Only SELECT or WITH ... SELECT statements are allowed"
        )

    # Fast-fail commands that should never be produced by the generator. The
    # SQLite authorizer remains the final enforcement layer, including malicious
    # CTE forms such as WITH ... DELETE/UPDATE/INSERT.
    forbidden_prefixes = {
        "ALTER",
        "ANALYZE",
        "ATTACH",
        "BEGIN",
        "COMMIT",
        "CREATE",
        "DELETE",
        "DETACH",
        "DROP",
        "INSERT",
        "PRAGMA",
        "REINDEX",
        "RELEASE",
        "REPLACE",
        "ROLLBACK",
        "SAVEPOINT",
        "UPDATE",
        "VACUUM",
    }
    if first in forbidden_prefixes:
        raise SqlSafetyError(f"Forbidden SQL statement type: {first}")

    return ValidatedSql(sql=sql.strip(), statement_kind=first)
