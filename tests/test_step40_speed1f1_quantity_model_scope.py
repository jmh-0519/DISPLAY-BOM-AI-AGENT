"""Compatibility regression for the superseded SPEED1F1 model-scope patch.

The original SPEED1F1 version required a model-code prompt before using an
already-viewed BOM. That policy was explicitly superseded by Active BOM Context
inheritance. This file is intentionally kept so old workspaces that still have
the filename are overwritten with the current policy instead of failing.
"""

from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.design_change_workflow_state import create_initial_design_change_state
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def test_item_only_quantity_change_without_active_bom_is_not_macro_dispatched():
    query = "LJ94-100006 자재의 수량을 바꾸고싶어 P01"
    gateway = BomGraphGateway()

    route = gateway.route({
        "messages": [HumanMessage(content=query)],
        "design_change": create_initial_design_change_state(),
    })

    assert route == AGENT_PATH


def test_explicit_model_scope_code_is_detected_by_current_router():
    router = DEFAULT_DOMAIN_INTENT_ROUTER
    query = (
        "LTA400HR01-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )

    assert router.explicit_model_scope_code(query) == "LTA400HR01-001"


def test_active_bom_context_allows_item_only_quantity_followup():
    node = BomAgentNode(Mock(), Mock(), "Phase3 workflow")
    query = "LJ94-100006 자재의 수량을 바꾸고싶어"

    result = node({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "active_bom_context": {
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
    })

    assert result["messages"][0].content == "변경할 수량을 입력해 주세요."
    pending = result["design_change"]["pending_quantity_request"]
    assert "LTA400HR01-001" in pending
    assert "P01" in pending
    assert "LJ94-100006" in pending
    node.client.create_agent_completion.assert_not_called()
    node.mcp_client.get_tool_definitions.assert_not_called()
