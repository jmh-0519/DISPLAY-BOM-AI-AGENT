from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.azure_openai_client import AzureOpenAIClient
from core.database_config import sqlite_database_path
from core.settings import Settings
from text_to_sql.evaluation import TextToSqlGenerationEvaluator
from text_to_sql.evaluation_cases import TextToSqlEvaluationCaseBuilder
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_generation import AzureSqlGenerationModel, SqlGenerator


DEFAULT_OUTPUT = "evaluation/text_to_sql/text_to_sql_generation_latest.json"


def _percent(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Azure OpenAI Text-to-SQL generation by executing "
            "generated and DB-v9 reference SQL against the same read-only database."
        )
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the Text-to-SQL quality gate fails.",
    )
    args = parser.parse_args()

    database_path = sqlite_database_path()
    catalog = SqlSchemaCatalog(database_path)
    cases = TextToSqlEvaluationCaseBuilder(catalog).build()

    azure_client = AzureOpenAIClient(Settings.from_env())
    generator = SqlGenerator(
        model=AzureSqlGenerationModel(azure_client),
        schema_catalog=catalog,
    )
    executor = ReadOnlySqlExecutor(database_path)

    summary = TextToSqlGenerationEvaluator(
        generator=generator,
        executor=executor,
    ).evaluate(cases)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            summary.as_dict(),
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("Text-to-SQL generation evaluation completed")
    print(f"- cases: {summary.case_count}")
    print(f"- sql_cases: {summary.sql_case_count}")
    print(f"- unsupported_cases: {summary.unsupported_case_count}")
    print(f"- passed: {summary.passed_count}/{summary.case_count}")
    print(f"- Overall Accuracy: {_percent(summary.overall_accuracy)}")
    print(f"- Status Accuracy: {_percent(summary.status_accuracy)}")
    print(
        "- SQL Execution Success: "
        f"{_percent(summary.sql_execution_success_rate)}"
    )
    print(
        "- Semantic Result Match: "
        f"{_percent(summary.semantic_match_rate)}"
    )
    print(
        "- UNSUPPORTED Accuracy: "
        f"{_percent(summary.unsupported_accuracy)}"
    )
    print(f"- Model Failures: {summary.model_failure_count}")
    print(
        "- Evaluator-only Tolerances: "
        f"{summary.evaluator_tolerance_count}"
    )
    print(f"- Evaluator Errors: {summary.evaluator_error_count}")
    print(
        "- Generation Latency P50: "
        f"{summary.generation_latency_p50_ms:.2f}ms"
    )
    print(
        "- Generation Latency P95: "
        f"{summary.generation_latency_p95_ms:.2f}ms"
    )
    print(f"- Gate: {'PASS' if summary.gate_pass else 'FAIL'}")
    print("- Category metrics:")
    for category, metrics in summary.category_metrics.items():
        print(
            f"  {category}: "
            f"cases={metrics['case_count']} "
            f"passed={metrics['passed_count']} "
            f"accuracy={_percent(float(metrics['accuracy']))}"
        )

    tolerances = [
        case
        for case in summary.cases
        if case.classification == "EVALUATOR_TOLERANCE"
    ]
    if tolerances:
        print("- Evaluator-tolerated cases:")
        for case in tolerances:
            print(
                f"  {case.case_id} [{case.category}] "
                "semantic=PASS strict=FAIL"
            )

    failures = [
        case for case in summary.cases
        if not case.passed
    ]
    if failures:
        print("- Failed cases:")
        for case in failures:
            print(
                f"  {case.case_id} [{case.category}] "
                f"expected={case.expected_status} "
                f"actual={case.actual_status} "
                f"classification={case.classification}"
            )
            print(f"    question: {case.question}")
            if case.error:
                print(f"    error: {case.error}")
            if case.reference_sql:
                print(f"    reference_sql: {case.reference_sql}")
            if case.generated_sql:
                print(f"    generated_sql: {case.generated_sql}")

    print(f"- report: {output_path.as_posix()}")

    if args.strict and not summary.gate_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
