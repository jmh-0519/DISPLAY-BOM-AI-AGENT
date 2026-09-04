from langchain_core.messages import AIMessage, HumanMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import (
    SCOPE_CONFLICT,
    BomGraphGateway,
)
from agents.design_change_workflow_state import (
    create_initial_design_change_state,
)


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


def _workflow():
    state = create_initial_design_change_state()
    state.update({
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-OLD",
        "plant_code": PLANT,
        "analysis_request": {
            "version_code": WORKFLOW_VERSION,
            "plant_code": PLANT,
        },
    })
    return state


def _state(query=RELATIVE_CHANGE, *, active_version=ACTIVE_VERSION):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": _workflow(),
        "active_bom_context": {
            "product_id": active_version,
            "plant_code": PLANT,
            "source": "get_bom",
        },
        "tool_steps": 0,
        "error": None,
    }


def test_relative_design_change_is_blocked_when_active_bom_differs_from_workflow():
    gateway = _gateway()
    state = _state()

    conflict = gateway.design_change_scope_conflict(state)

    assert conflict == {
        "active_version_code": ACTIVE_VERSION,
        "active_plant_code": PLANT,
        "workflow_version_code": WORKFLOW_VERSION,
        "workflow_plant_code": PLANT,
        "workflow_step": "ANALYSIS_READY",
    }
    assert gateway.route(state) == SCOPE_CONFLICT


def test_same_scope_relative_design_change_is_not_a_conflict():
    gateway = _gateway()
    state = _state(active_version=WORKFLOW_VERSION)

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_explicit_current_bom_model_resolves_scope_instead_of_conflict():
    gateway = _gateway()
    query = (
        f"{ACTIVE_VERSION} {PLANT} 모델에서 가장 원가가 높은 자재 1개를 찾고 "
        "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
    )
    state = _state(query)

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_explicit_active_bom_code_and_plant_resolve_without_model_suffix():
    gateway = _gateway()
    query = (
        f"{ACTIVE_VERSION} {PLANT} 대상으로 가장 원가가 높은 자재 1개를 "
        "찾아 변경 분석해줘"
    )
    state = _state(query)

    # No relative scope marker remains, so the old Workflow is not silently
    # selected by the conflict guard. The Graph-level workflow-composition
    # admission is covered in test_workflow_runtime_composition.py.
    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_explicit_existing_workflow_model_resolves_scope_instead_of_conflict():
    gateway = _gateway()
    query = (
        f"{WORKFLOW_VERSION} {PLANT} 모델의 기존 설계변경 분석 결과를 "
        "다시 설명해줘"
    )
    state = _state(query)

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_read_only_relative_question_is_not_blocked_by_design_change_guard():
    gateway = _gateway()
    state = _state("이 모델의 SEALANT 자재수량은 몇이야?")

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_non_relative_analysis_followup_can_still_use_workflow_context():
    gateway = _gateway()
    state = _state("왜 1번 후보가 FAIL이야?")

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_scope_conflict_node_returns_clarification_without_mutating_workflow():
    graph = object.__new__(BomAgentGraph)
    graph.gateway = _gateway()
    state = _state()

    update = graph._scope_conflict_node(state)

    assert "messages" in update
    assert isinstance(update["messages"][-1], AIMessage)
    assert not update["messages"][-1].tool_calls
    answer = update["messages"][-1].content
    assert ACTIVE_VERSION in answer
    assert WORKFLOW_VERSION in answer
    assert "상대 표현" in answer
    assert update["composition_runtime"] is None
    assert update["error"] is None
    assert "design_change" not in update
    assert "active_bom_context" not in update


def test_terminal_workflow_history_does_not_create_scope_conflict():
    gateway = _gateway()
    state = _state()
    workflow = dict(state["design_change"])
    workflow["current_step"] = "APPLIED"
    state["design_change"] = workflow

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_relative_assy_design_change_uses_same_scope_conflict_semantics():
    gateway = _gateway()
    state = _state("해당 ASSY를 변경할 때 적용되는 기준과 영향을 분석해줘")

    conflict = gateway.design_change_scope_conflict(state)

    assert conflict is not None
    assert conflict["active_version_code"] == ACTIVE_VERSION
    assert conflict["workflow_version_code"] == WORKFLOW_VERSION
    assert gateway.route(state) == SCOPE_CONFLICT


def test_workflow_analysis_reference_does_not_bind_to_active_bom_scope():
    gateway = _gateway()
    state = _state("기존 분석 결과를 설명해줘")

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) != SCOPE_CONFLICT


def test_explicit_bom_read_keeps_fast_read_semantics_during_active_analysis():
    gateway = _gateway()
    state = _state(f"{ACTIVE_VERSION} {PLANT} BOM 조회해줘")

    from agents.bom_graph_gateway import FAST_BOM_READ

    assert gateway.design_change_scope_conflict(state) is None
    assert gateway.route(state) == FAST_BOM_READ
