from __future__ import annotations

import argparse

from agents.bom_agent_graph import BomAgentGraph  # noqa: F401 - import smoke for project compatibility
from core.azure_openai_client import AzureOpenAIClient
from core.database_config import sqlite_database_path
from core.settings import Settings
from text_to_sql.pipeline import TextToSqlPipeline
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_generation import AzureSqlGenerationModel, SqlGenerator


DEFAULT_QUESTION = "활성 자재를 자재 그룹별로 몇 개씩 가지고 있는지 많은 순서대로 알려줘."


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one real Azure OpenAI natural-language-to-SQL smoke test."
    )
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    args = parser.parse_args()

    database_path = sqlite_database_path()
    azure_client = AzureOpenAIClient(Settings.from_env())
    generator = SqlGenerator(
        model=AzureSqlGenerationModel(azure_client),
        schema_catalog=SqlSchemaCatalog(database_path),
    )
    pipeline = TextToSqlPipeline(
        generator=generator,
        executor=ReadOnlySqlExecutor(database_path),
    )

    result = pipeline.run(args.question)

    print("Text-to-SQL LLM generation smoke test completed")
    print(f"- status: {result.status}")
    print(f"- question: {result.question}")
    print(f"- reason: {result.reason or '-'}")

    if result.status != "SQL":
        raise RuntimeError("Smoke question unexpectedly returned UNSUPPORTED")

    print("- generated_sql:")
    print(result.sql)
    print(f"- rows: {result.row_count}")
    print(f"- truncated: {result.truncated}")
    print(f"- elapsed_ms: {result.elapsed_ms:.2f}")
    for row in result.rows[:10]:
        print(f"  - {row}")


if __name__ == "__main__":
    main()
