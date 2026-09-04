from langchain_core.messages import HumanMessage

from agents.analysis_macro_dispatch import MACRO_ANALYZE
from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_BOM_READ,
    FAST_CHAT,
    FAST_WHERE_USED,
    BomGraphGateway,
)
from agents.design_change_workflow_state import create_initial_design_change_state


def _gateway():
    return BomGraphGateway(design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS)


def _state(query, workflow=None):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": workflow or create_initial_design_change_state(),
    }


def test_chat_enters_graph_fast_path():
    assert _gateway().route(_state("안녕하세요")) == FAST_CHAT


def test_explicit_bom_read_with_plant_enters_graph_fast_path():
    assert (
        _gateway().route(_state("LTA400HR01-001 P01 BOM 보여줘"))
        == FAST_BOM_READ
    )


def test_explicit_where_used_with_plant_enters_graph_fast_path():
    assert (
        _gateway().route(_state("P01에서 0001-310901 포함한 모델 알려줘"))
        == FAST_WHERE_USED
    )


def test_missing_plant_falls_back_to_agent_for_plant_gate():
    assert (
        _gateway().route(_state("LTA400HR01-001 BOM 보여줘"))
        == AGENT_PATH
    )


def test_design_change_never_enters_graph_read_fast_path():
    query = "LTA400HR01-001 P01에서 LJ94-100006 자재 수량을 3으로 변경해줘"
    # A high-confidence design change may bypass the LLM through the
    # deterministic Analysis Macro, but it must never enter a read-only Fast Path.
    assert _gateway().route(_state(query)) == MACRO_ANALYZE


def test_pending_quantity_slot_always_stays_on_agent_path():
    workflow = create_initial_design_change_state()
    workflow["pending_quantity_request"] = (
        "LTA400HR01-001 P01에서 LJ94-100006 자재 수량을 바꾸고싶어"
    )
    assert _gateway().route(_state("3", workflow)) == AGENT_PATH


def test_active_analysis_allows_explicit_bom_read_fast_path():
    workflow = create_initial_design_change_state()
    workflow["current_step"] = "ANALYSIS_READY"
    workflow["analysis_id"] = "ANA-1"
    assert (
        _gateway().route(_state("LTA400HR01-001 P01 BOM 보여줘", workflow))
        == FAST_BOM_READ
    )


def test_terminal_history_does_not_block_new_simple_read():
    workflow = create_initial_design_change_state()
    workflow["current_step"] = "APPLIED"
    workflow["analysis_id"] = "ANA-OLD"
    assert (
        _gateway().route(_state("LTA400HR01-001 P01 BOM 보여줘", workflow))
        == FAST_BOM_READ
    )


def test_terminal_fail_explanation_followup_stays_on_agent_path():
    workflow = create_initial_design_change_state()
    workflow["current_step"] = "BLOCKED"
    workflow["analysis_id"] = "ANA-FAIL"
    workflow["candidates"] = []
    assert _gateway().route(_state("왜 fail 이야?", workflow)) == AGENT_PATH


def test_pending_delete_target_slot_always_stays_on_agent_path():
    workflow = create_initial_design_change_state()
    workflow["pending_delete_target_request"] = {
        "version_code": "LTA400HR01-001",
        "plant_code": "P02",
    }
    assert _gateway().route(_state("0001-200003", workflow)) == AGENT_PATH
