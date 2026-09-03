from __future__ import annotations

from text_to_sql.pipeline import TextToSqlPipelineResult

from agents.workflow_evidence_handoff import (
    EvidenceToWorkflowHandoff,
    ResolvedWorkflowScope,
)


VERSION = "LTA400HR01-001"
PLANT = "P01"
AMBIGUOUS_GOAL = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)
UNIQUE_GOAL = (
    "이 모델에서 가장 원가가 높은 자재 1개를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


def _scope():
    return ResolvedWorkflowScope(
        version_code=VERSION,
        plant_code=PLANT,
        source="ACTIVE_BOM_CONTEXT",
    )


def _knowledge(authority=True):
    return {
        "success": True,
        "authority": {"knowledge_evidence_only": authority},
        "hits": [{
            "document_id": "COST",
            "document_title": "원가 절감",
            "section_path": "설계변경 기준",
        }],
    }


def _result(rows, row_count, sql):
    return TextToSqlPipelineResult(
        status="SQL",
        question=(
            f"{VERSION} {PLANT} 모델의 활성 BOM에서 "
            "현재 원가가 가장 높은 자재 1개"
        ),
        sql=sql,
        reason="",
        columns=tuple(rows[0].keys()) if rows else (),
        rows=tuple(rows),
        row_count=row_count,
        truncated=False,
        elapsed_ms=1.0,
    )


def main() -> None:
    handoff = EvidenceToWorkflowHandoff()
    good_sql = (
        "SELECT b.child_item_code AS item_code, ia.unit_cost "
        "FROM bom_master b "
        "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
        f"WHERE b.parent_item_code='{VERSION}' "
        f"AND b.plant_code='{PLANT}' "
        "ORDER BY ia.unit_cost DESC LIMIT 1"
    )

    cases = []

    cases.append((
        "PLAN03-E01",
        handoff.build(
            user_goal=AMBIGUOUS_GOAL,
            sql_result=_result(
                [{"item_code": "0001-200007", "unit_cost": 1200.0}],
                1,
                good_sql,
            ),
            knowledge_payload=_knowledge(),
            scope=_scope(),
        ),
        "USER_SELECTION_REQUIRED",
    ))

    cases.append((
        "PLAN03-E02",
        handoff.build(
            user_goal=UNIQUE_GOAL,
            sql_result=_result(
                [{"item_code": "0001-200007", "unit_cost": 1200.0}],
                1,
                good_sql,
            ),
            knowledge_payload=_knowledge(),
            scope=None,
        ),
        "SCOPE_REQUIRED",
    ))

    cases.append((
        "PLAN03-E03",
        handoff.build(
            user_goal=UNIQUE_GOAL,
            sql_result=_result(
                [{"item_code": "0001-200007", "unit_cost": 1200.0}],
                1,
                good_sql,
            ),
            knowledge_payload=_knowledge(),
            scope=_scope(),
        ),
        "READY",
    ))

    cases.append((
        "PLAN03-E04",
        handoff.build(
            user_goal=UNIQUE_GOAL,
            sql_result=_result(
                [
                    {"item_code": "0001-200007", "unit_cost": 1200.0},
                    {"item_code": "0001-200008", "unit_cost": 1190.0},
                ],
                2,
                good_sql,
            ),
            knowledge_payload=_knowledge(),
            scope=_scope(),
        ),
        "SQL_RESULT_AMBIGUOUS",
    ))

    missing_scope_sql = (
        "SELECT b.child_item_code AS item_code, ia.unit_cost "
        "FROM bom_master b "
        "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
        "ORDER BY ia.unit_cost DESC LIMIT 1"
    )
    cases.append((
        "PLAN03-E05",
        handoff.build(
            user_goal=UNIQUE_GOAL,
            sql_result=_result(
                [{"item_code": "0001-200007", "unit_cost": 1200.0}],
                1,
                missing_scope_sql,
            ),
            knowledge_payload=_knowledge(),
            scope=_scope(),
        ),
        "SQL_SCOPE_MISMATCH",
    ))

    cases.append((
        "PLAN03-E06",
        handoff.build(
            user_goal=UNIQUE_GOAL,
            sql_result=_result(
                [{"item_code": "0001-200007", "unit_cost": 1200.0}],
                1,
                good_sql,
            ),
            knowledge_payload=_knowledge(authority=False),
            scope=_scope(),
        ),
        "KNOWLEDGE_EVIDENCE_INVALID",
    ))

    failures = []
    for case_id, decision, expected in cases:
        actual = decision.status.value
        passed = actual == expected
        if not passed:
            failures.append(
                f"{case_id}: expected={expected} actual={actual}"
            )
        print(
            f"- {case_id} expected={expected} actual={actual} "
            f"ready={decision.ready}"
        )

    ready = cases[2][1]
    if ready.write_authority_granted:
        failures.append("READY case granted write authority")
    if ready.tool_name != "analyze_design_change_candidates":
        failures.append("READY case did not prepare Analysis tool")
    if (ready.tool_arguments or {}).get("request", {}).get("request_id"):
        failures.append("READY case unexpectedly created request_id")

    print(
        "PLAN-03 Evidence-to-Workflow Handoff "
        + ("PASS" if not failures else "FAIL")
    )
    print(f"case_count={len(cases)}")
    print(f"passed={len(cases) - len(failures)}")
    print(f"failed={len(failures)}")
    print("runtime_graph_modified=NO")
    print("analysis_tool_execution_enabled=NO")
    print("planner_llm_calls=0")
    print("request_creation_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
