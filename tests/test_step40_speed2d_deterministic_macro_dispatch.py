from langchain_core.messages import HumanMessage

from agents.analysis_macro_dispatch import (
    MACRO_ANALYZE,
    DeterministicAnalysisMacroDispatch,
)
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.bom_macro_dispatch_node import BomMacroDispatchNode


def _not_started():
    return {"current_step": "NOT_STARTED"}


def test_complete_replace_routes_to_macro_without_first_llm():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == MACRO_ANALYZE


def test_macro_node_builds_analysis_tool_call_from_explicit_scope():
    node = BomMacroDispatchNode()
    result = node({
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
            )
        ],
        "design_change": _not_started(),
    })

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert call["args"]["request"]["plant_code"] == "P01"
    assert call["args"]["actions"] == [{
        "action_type": "REPLACE",
        "target_item_name": "SEALANT",
    }]


def test_active_bom_scope_is_inherited_for_name_only_change():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query="SEALANT를 변경하고싶어",
        active_bom_context={
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
        workflow_state=_not_started(),
    )

    assert spec is not None
    assert spec["request"]["version_code"] == "LTA400HR01-001"
    assert spec["request"]["plant_code"] == "P01"
    assert spec["actions"][0]["target_item_name"] == "SEALANT"


def test_complete_quantity_change_routes_to_macro():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query=(
            "LTA400HR01-001 P01 모델에서 "
            "LJ94-100006 자재 수량을 3으로 바꿔줘"
        ),
        workflow_state=_not_started(),
    )

    assert spec is not None
    assert spec["actions"] == [{
        "action_type": "QUANTITY_CHANGE",
        "old_item_code": "LJ94-100006",
        "new_quantity": 3.0,
    }]


def test_incomplete_quantity_change_stays_on_agent_for_numeric_slot():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content=(
                    "LTA400HR01-001 P01 모델에서 "
                    "LJ94-100006 자재 수량을 바꾸고싶어"
                )
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == AGENT_PATH


def test_multiple_non_version_codes_stay_on_agent_to_avoid_old_new_guess():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content=(
                    "LTA400HR01-001 P01 모델에서 "
                    "0001-200010을 0002-210010으로 교체해줘"
                )
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == AGENT_PATH


def test_add_without_explicit_target_type_stays_on_agent_path():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 SEALANT를 추가해줘"
            )
        ],
        "design_change": _not_started(),
    }

    # ADD requires explicit MATERIAL/ASSY semantics for deterministic routing.
    assert gateway.route(state) == AGENT_PATH
