from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.design_change_workflow_state import create_initial_design_change_state


def _node():
    return BomAgentNode(Mock(), Mock(), "Design Change workflow")


def test_missing_quantity_sets_pending_slot_and_asks_only_quantity():
    node = _node()
    query = (
        "LTA400HR01-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )

    result = node({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
    })

    assert result["messages"][0].content == "변경할 수량을 입력해 주세요."
    assert result["design_change"]["pending_quantity_request"] == query


def test_pending_quantity_accepts_number_only():
    assert BomAgentNode._extract_quantity_only_input("2") == 2.0
    assert BomAgentNode._extract_quantity_only_input("2개") == 2.0
    assert BomAgentNode._extract_quantity_only_input("2.5") == 2.5


def test_pending_quantity_rejects_non_numeric_followup():
    assert BomAgentNode._extract_quantity_only_input("수량 2") is None
    assert BomAgentNode._extract_quantity_only_input("두개") is None
    assert BomAgentNode._extract_quantity_only_input("0") is None


def test_effective_query_restores_original_target_and_new_quantity():
    original = (
        "LTA400HR01-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )
    value = BomAgentNode._extract_quantity_only_input("2")
    effective = (
        f"{original} "
        f"수량을 {BomAgentNode._format_quantity(value)}로 변경해줘"
    )

    assert "LTA400HR01-001" in effective
    assert "P01" in effective
    assert "LJ94-100006" in effective
    assert BomAgentNode._extract_new_quantity(effective) == 2.0
    assert BomAgentNode._is_quantity_change_instruction(effective) is True
