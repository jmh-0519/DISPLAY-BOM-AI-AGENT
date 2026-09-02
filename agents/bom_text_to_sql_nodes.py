"""Dedicated LangGraph node for read-only Text-to-SQL analytics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from agents.bom_agent_state import BomAgentState
from core.database_config import sqlite_database_path
from text_to_sql.pipeline import TextToSqlPipeline, TextToSqlPipelineResult
from text_to_sql.query_router import (
    DEFAULT_TEXT_TO_SQL_QUERY_ROUTER,
    TextToSqlQueryRouter,
)
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_generation import AzureSqlGenerationModel, SqlGenerator


class BomTextToSqlPathNodes:
    """Generate + execute safe SQL and return an LLM-free deterministic answer."""

    MAX_RENDERED_ROWS = 30

    def __init__(
        self,
        *,
        client=None,
        database_path: str | Path | None = None,
        router: TextToSqlQueryRouter | None = None,
        pipeline: TextToSqlPipeline | None = None,
    ) -> None:
        self.router = router or DEFAULT_TEXT_TO_SQL_QUERY_ROUTER
        if pipeline is not None:
            self.pipeline = pipeline
            return
        if client is None:
            raise ValueError("client is required when pipeline is not supplied")

        path = Path(database_path) if database_path is not None else sqlite_database_path()
        self.pipeline = TextToSqlPipeline(
            generator=SqlGenerator(
                model=AzureSqlGenerationModel(client),
                schema_catalog=SqlSchemaCatalog(path),
            ),
            executor=ReadOnlySqlExecutor(path),
        )

    def query(self, state: BomAgentState) -> BomAgentState:
        user_query = self._last_user_query(state)
        decision = self.router.route(user_query)
        if not decision.eligible:
            raise ValueError("Text-to-SQL Path received a non-analytical request.")

        try:
            result = self.pipeline.run(user_query)
        except Exception:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "요청한 분석 조회를 안전하게 실행하지 못했습니다. "
                            "조회 조건이나 표현을 조금 더 구체적으로 입력해 주세요."
                        )
                    )
                ],
                "error": None,
            }

        return {
            "messages": [AIMessage(content=self._format_result(result))],
            "error": None,
        }

    @classmethod
    def _format_result(cls, result: TextToSqlPipelineResult) -> str:
        if result.status != "SQL":
            reason = str(result.reason or "").strip()
            return reason or (
                "이 요청은 현재 Text-to-SQL 읽기 전용 조회 범위에서 "
                "처리할 수 없습니다."
            )

        rows = list(result.rows)
        if not rows:
            return "조회 결과가 없습니다."

        columns = list(result.columns)
        visible_rows = rows[: cls.MAX_RENDERED_ROWS]

        lines = [
            f"조회 결과입니다. 총 {result.row_count}건입니다.",
            "",
            "| " + " | ".join(cls._escape_text(column) for column in columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        for row in visible_rows:
            lines.append(
                "| "
                + " | ".join(
                    cls._format_value(column, row.get(column))
                    for column in columns
                )
                + " |"
            )

        if len(rows) > cls.MAX_RENDERED_ROWS:
            lines.extend([
                "",
                f"화면에는 앞 {cls.MAX_RENDERED_ROWS}건만 표시했습니다. "
                f"전체 조회 건수는 {result.row_count}건입니다.",
            ])
        if result.truncated:
            lines.extend([
                "",
                "안전한 조회를 위해 최대 행 수 제한이 적용되었습니다.",
            ])
        return "\n".join(lines)

    @classmethod
    def _format_value(cls, column: str, value: Any) -> str:
        """Format result values for UI only; never alter SQL or DB values."""
        if value is None:
            return "-"

        column_name = str(column or "").strip().lower()

        if isinstance(value, bool):
            return str(value)

        if isinstance(value, int):
            return f"{value:,}"

        if isinstance(value, float):
            if value.is_integer():
                return f"{int(value):,}"

            # Monetary/cost metrics are displayed to two decimal places.
            if any(
                marker in column_name
                for marker in ("price", "cost", "amount", "단가", "금액", "원가")
            ):
                return f"{value:,.2f}"

            # Other analytical decimals keep useful precision without exposing
            # floating-point noise in the UI.
            return f"{value:,.4f}".rstrip("0").rstrip(".")

        return cls._escape_text(value)

    @staticmethod
    def _escape_text(value: Any) -> str:
        return (
            str(value)
            .replace("|", "\\|")
            .replace("\r", " ")
            .replace("\n", " ")
            .strip()
        )

    @staticmethod
    def _last_user_query(state: BomAgentState) -> str:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content or "").strip()
        return str(state.get("user_query") or "").strip()


__all__ = ["BomTextToSqlPathNodes"]
