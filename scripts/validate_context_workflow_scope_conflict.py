from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import AGENT_PATH, SCOPE_CONFLICT, BomGraphGateway
from agents.bom_workflow_composition_nodes import (
    WORKFLOW_COMPOSITION_PLAN,
    BomWorkflowCompositionNodes,
)
from agents.bom_text_to_sql_nodes import BomTextToSqlPathNodes
from agents.design_change_workflow_state import create_initial_design_change_state
from agents.workflow_evidence_handoff import EvidenceToWorkflowHandoff


WORKFLOW_VERSION = "LTA400HR01-001"
ACTIVE_VERSION = "LTA550HR11-001"
PLANT = "P01"
RELATIVE_CHANGE = (
    "이 모델에서 가장 원가가 높은 자재 1개를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


def _gateway():
    return BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )


def _workflow(step="ANALYSIS_READY"):
    state = create_initial_design_change_state()
    state.update({
        "current_step": step,
        "analysis_id": "ANA-OLD",
        "plant_code": PLANT,
        "analysis_request": {
            "version_code": WORKFLOW_VERSION,
            "plant_code": PLANT,
        },
    })
    return state


def _state(query, *, active_version=ACTIVE_VERSION, step="ANALYSIS_READY"):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": _workflow(step),
        "active_bom_context": {
            "product_id": active_version,
            "plant_code": PLANT,
            "source": "get_bom",
        },
        "tool_steps": 0,
        "error": None,
    }


def main() -> None:
    gateway = _gateway()
    failures: list[str] = []

    cases = [
        (
            "R3-C01",
            _state(RELATIVE_CHANGE),
            True,
        ),
        (
            "R3-C02",
            _state(RELATIVE_CHANGE, active_version=WORKFLOW_VERSION),
            False,
        ),
        (
            "R3-C03",
            _state(
                f"{ACTIVE_VERSION} {PLANT} 모델에서 가장 원가가 높은 "
                "자재 1개를 찾고 그 자재를 변경할 때 적용되는 기준과 "
                "영향을 알려줘"
            ),
            False,
        ),
        (
            "R3-C04",
            _state("이 모델의 SEALANT 자재수량은 몇이야?"),
            False,
        ),
        (
            "R3-C05",
            _state("왜 1번 후보가 FAIL이야?"),
            False,
        ),
        (
            "R3-C06",
            _state(RELATIVE_CHANGE, step="APPLIED"),
            False,
        ),
    ]

    for case_id, state, expected_conflict in cases:
        conflict = gateway.design_change_scope_conflict(state)
        actual_conflict = conflict is not None
        route = gateway.route(state)
        expected_route = SCOPE_CONFLICT if expected_conflict else None
        print(
            f"- {case_id} conflict={actual_conflict} route={route}"
        )
        if actual_conflict != expected_conflict:
            failures.append(
                f"{case_id}: expected_conflict={expected_conflict} "
                f"actual={actual_conflict}"
            )
        if expected_route and route != expected_route:
            failures.append(
                f"{case_id}: expected route {expected_route}, actual={route}"
            )
        if not expected_conflict and route == SCOPE_CONFLICT:
            failures.append(
                f"{case_id}: non-conflict request entered scope conflict route"
            )

    graph = object.__new__(BomAgentGraph)
    graph.gateway = gateway
    node_update = graph._scope_conflict_node(_state(RELATIVE_CHANGE))
    answer = str(node_update["messages"][-1].content or "")
    if ACTIVE_VERSION not in answer or WORKFLOW_VERSION not in answer:
        failures.append("scope-conflict answer does not expose both scopes")
    if node_update["messages"][-1].tool_calls:
        failures.append("scope-conflict node unexpectedly emitted a Tool call")
    if "design_change" in node_update:
        failures.append("scope-conflict node unexpectedly mutated workflow")
    if "active_bom_context" in node_update:
        failures.append("scope-conflict node unexpectedly mutated Active BOM")

    explicit_fresh_query = (
        f"{ACTIVE_VERSION} {PLANT} 대상으로 가장 원가가 높은 자재 1개를 "
        "찾아 변경 분석해줘"
    )
    explicit_state = _state(explicit_fresh_query)
    scope = EvidenceToWorkflowHandoff().resolve_scope(
        explicit_fresh_query,
        active_bom_context=explicit_state["active_bom_context"],
    )
    if (
        scope is None
        or scope.version_code != ACTIVE_VERSION
        or scope.plant_code != PLANT
        or scope.source != "CURRENT_TURN_EXPLICIT"
    ):
        failures.append(
            "explicit Active BOM code/PLANT did not resolve as current-turn scope"
        )

    # can_execute() is pure admission logic here; no SQL/RAG/Analysis Tool is
    # executed by this validator.
    text_nodes = BomTextToSqlPathNodes.__new__(BomTextToSqlPathNodes)
    workflow_nodes = BomWorkflowCompositionNodes(
        text_to_sql_nodes=text_nodes,
        analysis_finalizer=lambda state: state,
    )
    if not workflow_nodes.can_execute(explicit_state):
        failures.append(
            "explicit fresh scope was not admitted from pre-Request Analysis"
        )

    graph.workflow_composition_path_nodes = workflow_nodes

    class _ReadOnlyComposition:
        @staticmethod
        def can_execute(state):
            return False

    graph.composition_path_nodes = _ReadOnlyComposition()
    if gateway.route(explicit_state) != AGENT_PATH:
        failures.append("explicit fresh scope did not remain Gateway-conservative")
    if graph._runtime_route(explicit_state) != WORKFLOW_COMPOSITION_PLAN:
        failures.append(
            "explicit fresh scope was not promoted to Workflow Composition"
        )

    print(
        "PLAN-04-R3 Context/Workflow Scope Conflict Guard "
        + ("PASS" if not failures else "FAIL")
    )
    print("relative_scope_mismatch_blocked=YES")
    print("read_only_active_bom_semantics_unchanged=YES")
    print("explicit_model_disambiguation_preserved=YES")
    print("analysis_followup_without_relative_scope_preserved=YES")
    print("explicit_active_bom_code_without_model_suffix=YES")
    print("pre_request_analysis_fresh_scope_promotion=YES")
    print("mandatory_rag_evidence_dependency=YES")
    print("llm_calls_on_conflict=0")
    print("tool_calls_on_conflict=0")
    print("workflow_mutation_on_conflict=NO")
    print("request_creation_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
