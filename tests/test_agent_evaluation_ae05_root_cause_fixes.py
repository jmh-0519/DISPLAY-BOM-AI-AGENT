from __future__ import annotations

from pathlib import Path

from agents.domain_intent_router import DomainIntentRouter
from evaluation.dataset import load_evaluation_cases
from evaluation.evaluator import AgentAccuracyEvaluator
from evaluation.fixtures import EvaluationFixtureResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE = PROJECT_ROOT / "data" / "display_bom.db"


def _case(case_id: str):
    return next(case for case in load_evaluation_cases() if case.case_id == case_id)


def _observation(case_id: str, turn_index: int, *, intent: str, route: str, tool: str | None):
    calls = [] if tool is None else [{"name": tool, "arguments": {}, "tool_call_id": "ae05"}]
    return {
        "run_id": "ae05-test",
        "case_id": case_id,
        "turn_index": turn_index,
        "user_input": "test",
        "actual_intent": intent,
        "execution_path": route,
        "primary_tool": tool,
        "tool_calls": calls,
    }


def test_replace_wish_language_is_change_intent():
    router = DomainIntentRouter()
    decision = router.route("LTA400HR01-001 모델에서 DRIVE-IC 바꾸고 싶어")
    assert decision.intent == "PHASE3_CHANGE"
    assert decision.change is True


def test_replacement_candidate_recommendation_is_not_write_intent():
    router = DomainIntentRouter()
    decision = router.route("LTA400HR01-001 P02 DRIVE-IC 대체 후보 추천해줘")
    assert decision.intent == "PHASE3_RECOMMENDATION"
    assert decision.change is False


def test_candidate_analysis_wording_is_not_write_intent():
    router = DomainIntentRouter()
    decision = router.route("LTA400HR01-001 P02 0001-200003 교체 후보 분석해줘")
    assert decision.intent == "PHASE3_RECOMMENDATION"
    assert decision.change is False


def test_named_target_strips_reason_clause_and_generic_delete_target():
    router = DomainIntentRouter()
    assert (
        router.extract_named_change_target(
            "LTA400HR01-001 P02 DRIVE-IC가 단종이라 교체하고 싶어"
        )
        == "DRIVE-IC"
    )
    assert (
        router.extract_named_change_target(
            "LTA400HR01-001 P02 모델에서 자재 하나 삭제해줘"
        )
        is None
    )


def test_add_is_not_parsed_as_generic_source_target():
    router = DomainIntentRouter()
    assert (
        router.extract_named_change_target(
            "LTA400HR01-001 P02 모델에 BIN ASSY를 추가하고 싶어"
        )
        is None
    )


def test_plant_select_allows_read_only_resolution_tool():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("BOM_READ-003")
    observation = _observation(
        "BOM_READ-003",
        1,
        intent="BOM_READ",
        route="AGENT_PATH",
        tool="list_plants",
    )
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([observation])
    assert report.metrics["tool_selection"]["accuracy"] == 100.0


def test_clarify_allows_read_only_resolution_but_not_analysis_tool():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("CONTEXT-006")

    safe = _observation(
        "CONTEXT-006",
        1,
        intent="CURRENT_BOM_QUANTITY",
        route="AGENT_PATH",
        tool="search_material",
    )
    safe_report = AgentAccuracyEvaluator([case], fixtures).evaluate([safe])
    assert safe_report.metrics["tool_selection"]["accuracy"] == 100.0

    unsafe = _observation(
        "CONTEXT-006",
        1,
        intent="CURRENT_BOM_QUANTITY",
        route="AGENT_PATH",
        tool="analyze_design_change_candidates",
    )
    unsafe_report = AgentAccuracyEvaluator([case], fixtures).evaluate([unsafe])
    assert unsafe_report.metrics["tool_selection"]["accuracy"] == 0.0


def test_macro_uses_positional_model_scope_when_plant_and_target_are_explicit():
    from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch

    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query="LTA400HR01-001 P02 0001-200003 교체해줘",
        active_bom_context=None,
        workflow_state={},
    )
    assert spec is not None
    assert spec["request"]["version_code"] == "LTA400HR01-001"
    assert spec["request"]["plant_code"] == "P02"
    assert spec["actions"][0]["old_item_code"] == "0001-200003"


def test_read_only_quantity_followup_can_reuse_analysis_scope():
    from agents.bom_graph_gateway import BomGraphGateway

    scope = BomGraphGateway.read_scope_context({
        "active_bom_context": None,
        "design_change": {
            "plant_code": "P02",
            "analysis_request": {
                "version_code": "LTA400HR01-001",
                "plant_code": "P02",
            },
        },
    })
    assert scope == {"product_id": "LTA400HR01-001", "plant_code": "P02"}
