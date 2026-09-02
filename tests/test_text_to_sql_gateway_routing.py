from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_BOM_READ,
    FAST_KNOWLEDGE,
    FAST_TEXT_TO_SQL,
    FAST_WHERE_USED,
    BomGraphGateway,
)
from agents.design_change_workflow_state import create_initial_design_change_state


def _gateway():
    return BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )


def _state(query, workflow=None):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": workflow or create_initial_design_change_state(),
    }


def test_ad_hoc_analytics_routes_to_text_to_sql_without_agent_llm():
    assert (
        _gateway().route(_state("공급사별 평균 자재 단가를 낮은 순서대로 알려줘"))
        == FAST_TEXT_TO_SQL
    )


def test_existing_deterministic_bom_and_where_used_routes_keep_priority():
    assert _gateway().route(_state("LTA400HR01-001 P01 BOM 보여줘")) == FAST_BOM_READ
    assert (
        _gateway().route(_state("P01에서 0001-310901 포함한 모델 알려줘"))
        == FAST_WHERE_USED
    )


def test_knowledge_route_keeps_priority_over_text_to_sql():
    assert _gateway().route(_state("단종 자재 교체 기준이 뭐야?")) == FAST_KNOWLEDGE


def test_design_change_and_active_workflow_never_enter_text_to_sql():
    assert (
        _gateway().route(_state("LTA400HR01-001 P01 DRIVE-IC 교체해줘"))
        != FAST_TEXT_TO_SQL
    )

    workflow = create_initial_design_change_state()
    workflow["current_step"] = "ANALYSIS_READY"
    workflow["analysis_id"] = "ANA-1"
    assert (
        _gateway().route(_state("공급사별 평균 자재 단가를 알려줘", workflow))
        == AGENT_PATH
    )
