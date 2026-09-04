"""PLAN-05 generalized Evidence-driven Design Change composition validator.

This validator is intentionally read-only.  It verifies actual business-sample
semantics and the Analysis-only composition contract without calling an LLM or
mutating Design Change workflow/Production BOM data.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_text_to_sql_nodes import BomTextToSqlPathNodes
from agents.bom_workflow_composition_nodes import BomWorkflowCompositionNodes
from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementResolver,
)
from agents.design_change_workflow_state import create_initial_design_change_state
from agents.workflow_target_resolution import (
    TargetCriterion,
    TargetResolutionMode,
    WorkflowTargetResolutionPlanner,
)
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.workflow_target_evidence import (
    ScopedBomTargetEvidenceQuery,
    TargetQueryStatus,
)


DATABASE = Path("data/display_bom.db")
VERSION = "LTA400HR01-001"
NO_COST_VERSION = "LTA550HR11-001"
PLANT = "P01"
EXPECTED_HIGH_COST_ITEM = "0001-200008"
EXPECTED_HIGH_COST_PARENT = "LJ94-100003"
EXPECTED_HIGH_COST_LOCATION = "ALL"
EXPECTED_LOW_COST_ITEM = "0001-200012"

EXPLICIT_CODE_GOAL = (
    f"{VERSION} {PLANT} 모델에서 {EXPECTED_HIGH_COST_ITEM}을 변경할 때 "
    "적용되는 기준과 영향을 분석해줘"
)
EXPLICIT_NAME_GOAL = (
    f"{VERSION} {PLANT} 모델에서 SPACER를 다른 자재로 "
    "변경할 수 있는지 분석해줘"
)
COST_GOAL = (
    f"{VERSION} {PLANT} 모델에서 가장 원가가 높은 자재 1개를 "
    "찾아 변경 분석해줘"
)
NO_COST_GOAL = (
    f"{NO_COST_VERSION} {PLANT} 모델에서 가장 원가가 높은 자재 1개를 "
    "찾아 변경 분석해줘"
)
COMMONALITY_GOAL = (
    f"{VERSION} {PLANT} 모델에서 공용성이 가장 높은 자재 1개를 "
    "찾아 변경 분석해줘"
)
AMBIGUOUS_RANK_GOAL = (
    f"{VERSION} {PLANT} 모델에서 원가가 높은 자재들을 보고 "
    "적당한 걸 변경해줘"
)


class _NoGenerationPipeline:
    """Expose the real read-only executor but fail if SQL-generation is called."""

    def __init__(self, executor: ReadOnlySqlExecutor) -> None:
        self.executor = executor
        self.run_calls = 0

    def run(self, question):
        self.run_calls += 1
        raise AssertionError(
            f"PLAN-05 workflow target resolution must not call SQL generation: {question}"
        )


class _AnalysisFinalizer:
    def __call__(self, state):
        return {"messages": [AIMessage(content="analysis finalized")], "error": None}


def _state(query: str, *, version: str = VERSION) -> dict:
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "active_bom_context": {
            "product_id": version,
            "plant_code": PLANT,
            "source": "get_bom",
        },
        "tool_steps": 0,
        "error": None,
    }


def _knowledge_payload() -> dict:
    return {
        "success": True,
        "query": "설계변경 기준과 영향",
        "authority": {"knowledge_evidence_only": True},
        "hit_count": 1,
        "hits": [{
            "rank": 1,
            "document_id": "CHANGE-RULE",
            "document_title": "설계변경 기준",
            "document_type": "CHANGE_RULE",
            "section_path": "설계변경 기준",
            "content": "설계변경 분석은 기존 Rule/Service 권한으로 판정한다.",
        }],
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    _assert(DATABASE.exists(), f"Database not found: {DATABASE}")

    executor = ReadOnlySqlExecutor(DATABASE)
    evidence = ScopedBomTargetEvidenceQuery(executor)
    target_planner = WorkflowTargetResolutionPlanner()
    capability = CapabilityRequirementResolver()

    # Actual DB semantics: explicit target resolution.
    explicit_code = evidence.resolve_explicit(
        version_code=VERSION,
        plant_code=PLANT,
        item_code=EXPECTED_HIGH_COST_ITEM,
    )
    _assert(explicit_code.status == TargetQueryStatus.READY, "explicit code target failed")
    _assert(explicit_code.row["parent_item_code"] == EXPECTED_HIGH_COST_PARENT, "explicit parent mismatch")
    _assert(explicit_code.row["location_code"] == EXPECTED_HIGH_COST_LOCATION, "explicit location mismatch")

    explicit_name = evidence.resolve_explicit(
        version_code=VERSION,
        plant_code=PLANT,
        target_name="SPACER",
    )
    _assert(explicit_name.status == TargetQueryStatus.READY, "explicit name target failed")
    _assert(explicit_name.row["item_code"] == EXPECTED_HIGH_COST_ITEM, "explicit name item mismatch")

    high = evidence.resolve_cost_rank(
        version_code=VERSION,
        plant_code=PLANT,
        direction="HIGH",
    )
    low = evidence.resolve_cost_rank(
        version_code=VERSION,
        plant_code=PLANT,
        direction="LOW",
    )
    no_cost = evidence.resolve_cost_rank(
        version_code=NO_COST_VERSION,
        plant_code=PLANT,
        direction="HIGH",
    )
    commonality = evidence.resolve_commonality_rank(
        version_code=VERSION,
        plant_code=PLANT,
    )

    _assert(high.status == TargetQueryStatus.READY, "high-cost target failed")
    _assert(high.row["item_code"] == EXPECTED_HIGH_COST_ITEM, "high-cost item mismatch")
    _assert(low.status == TargetQueryStatus.READY, "low-cost target failed")
    _assert(low.row["item_code"] == EXPECTED_LOW_COST_ITEM, "low-cost item mismatch")
    _assert(no_cost.status == TargetQueryStatus.EMPTY, "missing cost must remain empty")
    _assert(commonality.status == TargetQueryStatus.AMBIGUOUS, "sample commonality tie must be ambiguous")

    # Deterministic intent/capability contract.
    explicit_requirement = capability.resolve(EXPLICIT_CODE_GOAL)
    _assert(
        explicit_requirement.capabilities == (
            Capability.RAG,
            Capability.DESIGN_CHANGE_ANALYSIS,
        ),
        f"explicit capability mismatch: {explicit_requirement.capability_names}",
    )
    cost_requirement = capability.resolve(COST_GOAL)
    _assert(
        cost_requirement.capabilities == (
            Capability.TEXT_TO_SQL,
            Capability.RAG,
            Capability.DESIGN_CHANGE_ANALYSIS,
        ),
        f"cost capability mismatch: {cost_requirement.capability_names}",
    )

    explicit_plan = target_planner.resolve(
        EXPLICIT_CODE_GOAL,
        scope_version_code=VERSION,
    )
    named_plan = target_planner.resolve(
        EXPLICIT_NAME_GOAL,
        scope_version_code=VERSION,
    )
    cost_plan = target_planner.resolve(COST_GOAL, scope_version_code=VERSION)
    commonality_plan = target_planner.resolve(
        COMMONALITY_GOAL,
        scope_version_code=VERSION,
    )
    ambiguous_plan = target_planner.resolve(
        AMBIGUOUS_RANK_GOAL,
        scope_version_code=VERSION,
    )

    _assert(explicit_plan.ready and explicit_plan.request.mode == TargetResolutionMode.EXPLICIT, "explicit plan not ready")
    _assert(named_plan.ready and named_plan.request.explicit_target_name == "SPACER", "named target extraction failed")
    _assert(cost_plan.ready and cost_plan.request.criterion == TargetCriterion.COST, "cost target plan failed")
    _assert(commonality_plan.ready and commonality_plan.request.criterion == TargetCriterion.COMMONALITY, "commonality target plan failed")
    _assert(not ambiguous_plan.ready and ambiguous_plan.request is None, "ambiguous rank was auto-selected")

    # Runtime composition: explicit target bypasses Text-to-SQL generation.
    pipeline = _NoGenerationPipeline(executor)
    nodes = BomWorkflowCompositionNodes(
        text_to_sql_nodes=BomTextToSqlPathNodes(pipeline=pipeline),
        analysis_finalizer=_AnalysisFinalizer(),
    )
    state = _state(EXPLICIT_CODE_GOAL)
    _assert(nodes.can_execute(state), "explicit workflow composition was not admitted")
    state.update(nodes.plan(state))
    runtime = state["composition_runtime"]
    _assert(runtime["target_request"]["mode"] == "EXPLICIT", "explicit runtime mode mismatch")
    _assert("TEXT_TO_SQL" not in runtime["queries"], "explicit target unexpectedly requested Text-to-SQL")

    state.update(nodes.resolve_explicit_target(state))
    runtime = state["composition_runtime"]
    _assert(runtime["status"] == "TARGET_RESOLVED", "explicit target was not resolved")
    _assert(runtime["target_evidence"]["item_code"] == EXPECTED_HIGH_COST_ITEM, "explicit runtime item mismatch")
    _assert(pipeline.run_calls == 0, "explicit target called SQL-generation pipeline")

    knowledge_update = nodes.knowledge_query(state)
    state["messages"] += knowledge_update["messages"]
    state["composition_runtime"] = knowledge_update["composition_runtime"]
    knowledge_call = state["messages"][-1].tool_calls[0]
    _assert(knowledge_call["name"] == "search_knowledge", "RAG tool was not dispatched")
    state["messages"].append(ToolMessage(
        content=json.dumps(_knowledge_payload(), ensure_ascii=False),
        tool_call_id=knowledge_call["id"],
        name="search_knowledge",
    ))
    handoff_update = nodes.handoff_and_dispatch(state)
    analysis_call = handoff_update["messages"][-1].tool_calls[0]
    _assert(analysis_call["name"] == "analyze_design_change_candidates", "Analysis tool was not dispatched")
    _assert(analysis_call["args"]["actions"] == [{
        "action_type": "REPLACE",
        "old_item_code": EXPECTED_HIGH_COST_ITEM,
        "parent_item_code": EXPECTED_HIGH_COST_PARENT,
        "location_code": EXPECTED_HIGH_COST_LOCATION,
    }], "exact BOM edge handoff mismatch")
    _assert("request_id" not in analysis_call["args"]["request"], "Request authority leaked into Analysis handoff")
    handoff = handoff_update["composition_runtime"]["handoff"]
    _assert(handoff["write_authority_granted"] is False, "write authority was granted")
    _assert(handoff["request_creation_allowed"] is False, "Request creation authority was granted")
    _assert(handoff["approval_allowed"] is False, "approval authority was granted")
    _assert(handoff["production_write_allowed"] is False, "Production write authority was granted")

    # Runtime deterministic analytics remains LLM-free and stops before RAG if
    # factual evidence is missing/ambiguous.
    cost_state = _state(COST_GOAL)
    cost_state.update(nodes.plan(cost_state))
    cost_state.update(nodes.text_to_sql(cost_state))
    _assert(cost_state["composition_runtime"]["status"] == "TARGET_RESOLVED", "cost target runtime failed")
    _assert(cost_state["composition_runtime"]["target_evidence"]["item_code"] == EXPECTED_HIGH_COST_ITEM, "cost runtime target mismatch")
    _assert(pipeline.run_calls == 0, "cost target called SQL-generation pipeline")

    no_cost_state = _state(NO_COST_GOAL, version=NO_COST_VERSION)
    no_cost_state.update(nodes.plan(no_cost_state))
    no_cost_update = nodes.text_to_sql(no_cost_state)
    _assert(no_cost_update["composition_runtime"] is None, "no-cost case advanced past evidence gate")
    _assert(not no_cost_update["messages"][-1].tool_calls, "no-cost case dispatched a Tool")

    common_state = _state(COMMONALITY_GOAL)
    common_state.update(nodes.plan(common_state))
    common_update = nodes.text_to_sql(common_state)
    _assert(common_update["composition_runtime"] is None, "commonality tie advanced past ambiguity gate")
    _assert(not common_update["messages"][-1].tool_calls, "commonality tie dispatched a Tool")

    print("PLAN-05 Generalized Evidence-driven Design Change Composition PASS")
    print("explicit_code_target=READY")
    print("explicit_name_target=READY")
    print("explicit_path_text_to_sql=NO")
    print("explicit_path_rag_required=YES")
    print(f"high_cost_target={EXPECTED_HIGH_COST_ITEM}")
    print(f"low_cost_target={EXPECTED_LOW_COST_ITEM}")
    print(f"no_cost_case={NO_COST_VERSION}/{PLANT}:BLOCKED_BEFORE_RAG")
    print("commonality_sample_tie=USER_SELECTION_REQUIRED")
    print("ambiguous_target_auto_selection=NO")
    print("recursive_bom_target_resolution=YES")
    print("exact_parent_location_handoff=YES")
    print(f"sql_generation_llm_calls={pipeline.run_calls}")
    print("analysis_session_only=YES")
    print("request_creation_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")


if __name__ == "__main__":
    main()
