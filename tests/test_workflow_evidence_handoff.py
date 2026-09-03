from text_to_sql.pipeline import TextToSqlPipelineResult

from agents.workflow_evidence_handoff import (
    EvidenceToWorkflowHandoff,
    HandoffStatus,
    ResolvedWorkflowScope,
)


GOAL_AMBIGUOUS = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)
GOAL_TOP1 = (
    "이 모델에서 가장 원가가 높은 자재 1개를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)
VERSION = "LTA400HR01-001"
PLANT = "P01"


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
        "hit_count": 1,
        "hits": [{
            "rank": 1,
            "document_id": "COST",
            "document_title": "원가 절감",
            "section_path": "설계변경 기준",
            "content": "원가 절감 변경 기준",
        }],
    }


def _sql_result(
    *,
    rows=({"item_code": "0001-200007", "unit_cost": 1200.0},),
    row_count=1,
    truncated=False,
    sql=None,
):
    return TextToSqlPipelineResult(
        status="SQL",
        question=(
            f"{VERSION} {PLANT} 모델의 활성 BOM에서 "
            "가장 원가가 높은 자재 1개"
        ),
        sql=sql or (
            "SELECT b.child_item_code AS item_code, ia.unit_cost "
            "FROM bom_master b "
            "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
            f"WHERE b.parent_item_code='{VERSION}' "
            f"AND b.plant_code='{PLANT}' "
            "ORDER BY ia.unit_cost DESC LIMIT 1"
        ),
        reason="",
        columns=("item_code", "unit_cost"),
        rows=tuple(rows),
        row_count=row_count,
        truncated=truncated,
        elapsed_ms=1.0,
    )


def test_current_diagnostic_wording_requires_user_selection():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_AMBIGUOUS,
        sql_result=_sql_result(),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.USER_SELECTION_REQUIRED
    assert decision.ready is False
    assert decision.tool_arguments is None


def test_implicit_this_model_can_use_active_bom_scope():
    handoff = EvidenceToWorkflowHandoff()
    scope = handoff.resolve_scope(
        GOAL_TOP1,
        active_bom_context={
            "product_id": VERSION,
            "plant_code": PLANT,
        },
    )
    assert scope is not None
    assert scope.version_code == VERSION
    assert scope.plant_code == PLANT
    assert scope.source == "ACTIVE_BOM_CONTEXT"


def test_explicit_model_without_plant_never_reuses_stale_active_plant():
    handoff = EvidenceToWorkflowHandoff()
    goal = (
        f"{VERSION} 모델에서 가장 원가가 높은 자재 1개를 찾고 "
        "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
    )
    scope = handoff.resolve_scope(
        goal,
        active_bom_context={
            "product_id": VERSION,
            "plant_code": PLANT,
        },
    )
    assert scope is None


def test_explicit_model_and_plant_resolve_current_turn_scope():
    handoff = EvidenceToWorkflowHandoff()
    goal = (
        f"{VERSION} {PLANT} 모델에서 가장 원가가 높은 자재 1개를 찾고 "
        "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
    )
    scope = handoff.resolve_scope(goal)
    assert scope is not None
    assert scope.version_code == VERSION
    assert scope.plant_code == PLANT
    assert scope.source == "CURRENT_TURN_EXPLICIT"


def test_ready_handoff_prepares_analysis_only_tool_contract():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )

    assert decision.status == HandoffStatus.READY
    assert decision.ready is True
    assert decision.tool_name == "analyze_design_change_candidates"
    assert decision.tool_arguments == {
        "request": {
            "version_code": VERSION,
            "plant_code": PLANT,
            "original_request": GOAL_TOP1,
        },
        "actions": [{
            "action_type": "REPLACE",
            "old_item_code": "0001-200007",
        }],
    }
    assert decision.analytics_evidence.item_code == "0001-200007"
    assert decision.analytics_evidence.metric_name == "unit_cost"
    assert decision.analytics_evidence.metric_value == 1200.0
    assert decision.knowledge_evidence.hit_count == 1
    assert decision.write_authority_granted is False
    assert decision.request_creation_allowed is False
    assert decision.approval_allowed is False
    assert decision.production_write_allowed is False


def test_multiple_sql_rows_never_become_one_change_target():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(
            rows=(
                {"item_code": "0001-200007", "unit_cost": 1200.0},
                {"item_code": "0001-200008", "unit_cost": 1190.0},
            ),
            row_count=2,
        ),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.SQL_RESULT_AMBIGUOUS
    assert decision.tool_arguments is None


def test_truncated_sql_result_is_never_handoff_evidence():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(truncated=True),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.SQL_RESULT_TRUNCATED


def test_sql_must_prove_descending_top_one_selection():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(
            sql=(
                "SELECT b.child_item_code AS item_code, ia.unit_cost "
                "FROM bom_master b "
                "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
                f"WHERE b.parent_item_code='{VERSION}' "
                f"AND b.plant_code='{PLANT}' "
                "LIMIT 1"
            )
        ),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.SQL_SELECTION_NOT_PROVEN


def test_sql_must_contain_both_version_and_plant_scope():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(
            sql=(
                "SELECT b.child_item_code AS item_code, ia.unit_cost "
                "FROM bom_master b "
                "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
                f"WHERE b.parent_item_code='{VERSION}' "
                "ORDER BY ia.unit_cost DESC LIMIT 1"
            )
        ),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.SQL_SCOPE_MISMATCH


def test_conflicting_item_code_columns_are_ambiguous():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(rows=({
            "item_code": "0001-200007",
            "child_item_code": "0001-200008",
            "unit_cost": 1200.0,
        },)),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.ITEM_CODE_AMBIGUOUS


def test_missing_cost_metric_blocks_handoff():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(rows=({
            "item_code": "0001-200007",
            "item_name": "SEALANT",
        },)),
        knowledge_payload=_knowledge(),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.COST_METRIC_REQUIRED


def test_rag_authority_must_remain_evidence_only():
    decision = EvidenceToWorkflowHandoff().build(
        user_goal=GOAL_TOP1,
        sql_result=_sql_result(),
        knowledge_payload=_knowledge(authority=False),
        scope=_scope(),
    )
    assert decision.status == HandoffStatus.KNOWLEDGE_EVIDENCE_INVALID
    assert decision.tool_arguments is None


def test_scoped_analytics_question_is_generated_only_for_unique_goal():
    handoff = EvidenceToWorkflowHandoff()

    assert handoff.build_scoped_analytics_question(
        GOAL_AMBIGUOUS,
        scope=_scope(),
    ) is None

    question = handoff.build_scoped_analytics_question(
        GOAL_TOP1,
        scope=_scope(),
    )
    assert question is not None
    assert VERSION in question
    assert PLANT in question
    assert "1개" in question
    assert "자재코드" in question
