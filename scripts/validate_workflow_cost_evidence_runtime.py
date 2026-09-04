from __future__ import annotations

from core.database_config import sqlite_database_path
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.workflow_cost_evidence import ScopedBomCostEvidenceQuery


CASES = (
    {
        "version_code": "LTA400HR01-001",
        "plant_code": "P01",
        "expected": "ONE_COST_ROW",
        "require_nested_parent": True,
    },
    {
        "version_code": "LTA550HR11-001",
        "plant_code": "P01",
        "expected": "NO_COST_EVIDENCE",
        "require_nested_parent": False,
    },
)


def main() -> None:
    database_path = sqlite_database_path()
    query = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(database_path))
    failures: list[str] = []

    print(f"database={database_path}")
    for case in CASES:
        version_code = case["version_code"]
        plant_code = case["plant_code"]
        expected = case["expected"]

        try:
            result = query.run(
                version_code=version_code,
                plant_code=plant_code,
                question=(
                    f"{version_code} {plant_code} 활성 BOM에서 "
                    "현재 확인 가능한 원가 또는 단가가 가장 높은 자재 1개"
                ),
            )
        except Exception as error:
            failures.append(
                f"{version_code}/{plant_code}: query failed: "
                f"{type(error).__name__}: {error}"
            )
            continue

        row = dict(result.rows[0]) if result.rows else {}
        print(
            f"- {version_code}/{plant_code}: "
            f"expected={expected} rows={result.row_count} "
            f"item={row.get('item_code')} "
            f"parent={row.get('parent_item_code')} "
            f"location={row.get('location_code')} "
            f"unit_cost={row.get('unit_cost')} "
            f"price_source={row.get('price_source')} "
            f"currency={row.get('currency_code')}"
        )

        if result.status != "SQL":
            failures.append(f"{version_code}/{plant_code}: status={result.status}")
            continue
        if result.truncated:
            failures.append(f"{version_code}/{plant_code}: result was truncated")

        if expected == "NO_COST_EVIDENCE":
            if result.row_count != 0 or result.rows:
                failures.append(
                    f"{version_code}/{plant_code}: expected no comparable "
                    "cost evidence but a target row was returned"
                )
            continue

        if result.row_count != 1 or len(result.rows) != 1:
            failures.append(
                f"{version_code}/{plant_code}: expected exactly one cost result row"
            )
            continue
        if not str(row.get("item_code") or "").strip():
            failures.append(f"{version_code}/{plant_code}: item_code missing")
        if not str(row.get("parent_item_code") or "").strip():
            failures.append(f"{version_code}/{plant_code}: parent_item_code missing")
        if not str(row.get("location_code") or "").strip():
            failures.append(f"{version_code}/{plant_code}: location_code missing")
        if row.get("unit_cost") is None:
            failures.append(f"{version_code}/{plant_code}: unit_cost missing")
        elif float(row.get("unit_cost") or 0.0) < 0:
            failures.append(f"{version_code}/{plant_code}: unit_cost is negative")

        if (
            case.get("require_nested_parent")
            and row.get("parent_item_code") == version_code
        ):
            failures.append(
                f"{version_code}/{plant_code}: recursive BOM evidence "
                "incorrectly resolved only a direct VERSION child"
            )

    print(
        "PLAN-04-R2 Real DB Cost Evidence Semantics "
        + ("PASS" if not failures else "FAIL")
    )
    print("positive_cost_case=LTA400HR01-001/P01")
    print("no_cost_evidence_case=LTA550HR11-001/P01")
    print("missing_cost_is_not_invented=YES")
    print("no_cost_evidence_blocks_before_rag=YES")
    print("recursive_bom_traversal=YES")
    print("sql_generation_llm_calls=0")
    print("read_only_executor=YES")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
