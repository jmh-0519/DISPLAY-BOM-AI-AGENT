from __future__ import annotations

from collections import Counter

from core.database_config import sqlite_database_path
from text_to_sql.evaluation_cases import TextToSqlEvaluationCaseBuilder
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.schema_catalog import SqlSchemaCatalog


def main() -> None:
    database_path = sqlite_database_path()
    catalog = SqlSchemaCatalog(database_path)
    cases = TextToSqlEvaluationCaseBuilder(catalog).build()
    executor = ReadOnlySqlExecutor(database_path)

    sql_cases = [
        case for case in cases
        if case.expected_status == "SQL"
    ]
    unsupported_cases = [
        case for case in cases
        if case.expected_status == "UNSUPPORTED"
    ]

    if len(cases) != 23 or len(sql_cases) != 15 or len(unsupported_cases) != 8:
        raise RuntimeError(
            "R1 evaluation shape mismatch: "
            f"total={len(cases)} sql={len(sql_cases)} "
            f"unsupported={len(unsupported_cases)}"
        )

    for case in sql_cases:
        executor.execute(case.reference_sql or "")

    categories = Counter(case.category for case in cases)

    print("Text-to-SQL evaluation dataset validation passed")
    print(f"- database: {database_path}")
    print(f"- cases: {len(cases)}")
    print(f"- sql_cases: {len(sql_cases)}")
    print(f"- unsupported_cases: {len(unsupported_cases)}")
    print(f"- reference_sql_execution: {len(sql_cases)}/{len(sql_cases)} PASS")
    print("- categories:")
    for category, count in sorted(categories.items()):
        print(f"  - {category}: {count}")
    print("- SQL cases:")
    for case in sql_cases:
        order = (
            f" order_key={case.order_key}"
            if case.order_key
            else ""
        )
        print(f"  - {case.case_id}: {case.question}{order}")
    print("- UNSUPPORTED cases:")
    for case in unsupported_cases:
        print(f"  - {case.case_id} [{case.category}]: {case.question}")


if __name__ == "__main__":
    main()
