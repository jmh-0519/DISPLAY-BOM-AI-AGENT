from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.sql_generation import SqlGenerator


@dataclass(frozen=True)
class TextToSqlPipelineResult:
    status: str
    question: str
    sql: str | None
    reason: str
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: float = 0.0


class TextToSqlPipeline:
    """Generate, validate and execute a read-only SQL candidate."""

    def __init__(
        self,
        *,
        generator: SqlGenerator,
        executor: ReadOnlySqlExecutor,
    ) -> None:
        self.generator = generator
        self.executor = executor

    def run(self, question: str) -> TextToSqlPipelineResult:
        generated = self.generator.generate(question)

        if not generated.is_sql:
            return TextToSqlPipelineResult(
                status="UNSUPPORTED",
                question=str(question),
                sql=None,
                reason=generated.reason,
            )

        execution = self.executor.execute(generated.sql or "")
        return TextToSqlPipelineResult(
            status="SQL",
            question=str(question),
            sql=generated.sql,
            reason=generated.reason,
            columns=execution.columns,
            rows=execution.rows,
            row_count=execution.row_count,
            truncated=execution.truncated,
            elapsed_ms=execution.elapsed_ms,
        )


__all__ = ["TextToSqlPipeline", "TextToSqlPipelineResult"]
