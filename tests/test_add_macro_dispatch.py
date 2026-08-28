from langchain_core.messages import HumanMessage

from agents.analysis_macro_dispatch import (
    MACRO_ANALYZE,
    DeterministicAnalysisMacroDispatch,
)
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.bom_macro_dispatch_node import BomMacroDispatchNode
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def _not_started():
    return {"current_step": "NOT_STARTED"}


def test_router_extracts_material_add_slots():
    router = DEFAULT_DOMAIN_INTENT_ROUTER
    query = "LTA400HR01-001 P01 모델에 SEALANT 자재를 추가하고싶어"

    assert router.extract_add_target_type(query) == "MATERIAL"
    assert router.extract_add_target_name(query) == "SEALANT"


def test_complete_material_add_routes_directly_to_macro():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 SEALANT 자재를 추가하고싶어"
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == MACRO_ANALYZE


def test_material_add_macro_uses_existing_version_default_parent_policy():
    node = BomMacroDispatchNode()
    result = node({
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 SEALANT 자재를 추가하고싶어"
            )
        ],
        "design_change": _not_started(),
    })

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert call["args"]["request"]["plant_code"] == "P01"
    assert call["args"]["actions"] == [{
        "action_type": "ADD",
        "target_type": "MATERIAL",
        "target_item_name": "SEALANT",
    }]



def test_generic_material_add_stays_on_clarification_path_without_target_name():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 자재를 추가하고 싶어"
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == AGENT_PATH

    spec = DeterministicAnalysisMacroDispatch().build_spec(
        user_query="LTA400HR01-001 P01 모델에 자재를 추가하고 싶어",
        workflow_state=_not_started(),
    )
    assert spec is None

def test_assy_add_without_parent_stays_on_agent_path():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 OLB ASSY를 추가해줘"
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == AGENT_PATH


def test_assy_add_with_explicit_parent_routes_to_macro():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query=(
            "LTA400HR01-001 P01 모델에서 "
            "LJ94-100001 아래에 OLB ASSY를 추가해줘"
        ),
        workflow_state=_not_started(),
    )

    assert spec is not None
    assert spec["actions"] == [{
        "action_type": "ADD",
        "target_type": "ASSY",
        "target_item_name": "OLB",
        "parent_item_code": "LJ94-100001",
    }]


def test_generic_item_word_does_not_guess_add_target_type():
    gateway = BomGraphGateway()
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에 SEALANT 품목을 추가해줘"
            )
        ],
        "design_change": _not_started(),
    }

    assert gateway.route(state) == AGENT_PATH


def test_quoted_generic_material_add_does_not_extract_quote_as_target_name():
    router = DEFAULT_DOMAIN_INTENT_ROUTER
    query = '"LTA400HR01-001 P01 모델에 자재를 추가하고 싶어"'
    assert router.extract_add_target_type(query) == "MATERIAL"
    assert router.extract_add_target_name(query) is None


def test_explicit_material_code_add_routes_to_macro():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query="LTA400HR01-001 P01 모델에 0001-200007 자재를 추가해줘",
        workflow_state=_not_started(),
    )
    assert spec is not None
    assert spec["actions"] == [{
        "action_type": "ADD",
        "target_type": "MATERIAL",
        "new_item_code": "0001-200007",
    }]
