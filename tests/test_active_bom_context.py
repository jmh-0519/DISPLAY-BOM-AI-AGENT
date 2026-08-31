from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER
from agents.bom_mcp_tool_node import BomMcpToolNode
from agents.design_change_workflow_state import create_initial_design_change_state


def _agent():
    return BomAgentNode(Mock(), Mock(), "Design Change workflow")



def test_item_only_quantity_change_without_active_bom_uses_agent_path():
    query = "LJ94-100006 자재의 수량을 바꾸고싶어 P01"
    route = BomGraphGateway().route({
        "messages": [HumanMessage(content=query)],
        "design_change": create_initial_design_change_state(),
    })
    assert route == AGENT_PATH


def test_explicit_model_scope_code_is_detected_by_router():
    query = "LTA400HR01-001 P01 모델에서 LJ94-100006 자재의 수량을 바꾸고싶어"
    assert DEFAULT_DOMAIN_INTENT_ROUTER.explicit_model_scope_code(query) == "LTA400HR01-001"

def test_item_only_quantity_change_inherits_current_active_bom_and_asks_only_quantity():
    node = _agent()
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


def test_explicit_different_plant_does_not_inherit_old_bom_scope():
    node = _agent()
    query = "P02에서 LJ94-100006 자재의 수량을 바꾸고싶어"

    enriched = node._inherit_active_bom_context_for_change(
        user_query=query,
        workflow_state=create_initial_design_change_state(),
        active_bom_context={
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
    )

    assert enriched == query


def test_explicit_different_model_does_not_inherit_old_bom_scope():
    node = _agent()
    query = (
        "LTA750HR11-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )

    enriched = node._inherit_active_bom_context_for_change(
        user_query=query,
        workflow_state=create_initial_design_change_state(),
        active_bom_context={
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
    )

    assert enriched == query


def test_get_bom_tool_result_sets_active_bom_context():
    mcp = Mock()
    mcp.call_tool.return_value = [
        {
            "PLANT": "P01",
            "PARENT_CODE": "LTA400HR01-001",
            "CHILD_CODE": "LJ94-100001",
        }
    ]
    node = BomMcpToolNode(mcp_client=mcp, observability=Mock())
    node.observability.observe.return_value.__enter__ = Mock(
        return_value=Mock(finish=Mock())
    )
    node.observability.observe.return_value.__exit__ = Mock(return_value=False)

    tool_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "get_bom",
            "args": {
                "plant_code": "P01",
                "product_id": "LTA400HR01-001",
            },
            "id": "test-get-bom",
            "type": "tool_call",
        }],
    )

    result = node({
        "messages": [tool_call],
        "tool_steps": 0,
        "design_change": create_initial_design_change_state(),
    })

    assert result["active_bom_context"] == {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }


def test_where_used_clears_single_product_active_bom_context():
    mcp = Mock()
    mcp.call_tool.return_value = {
        "item_code": "0001-310901",
        "top_models": [],
    }
    node = BomMcpToolNode(mcp_client=mcp, observability=Mock())
    node.observability.observe.return_value.__enter__ = Mock(
        return_value=Mock(finish=Mock())
    )
    node.observability.observe.return_value.__exit__ = Mock(return_value=False)

    tool_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "get_bom_where_used",
            "args": {
                "plant_code": "P01",
                "item_code": "0001-310901",
            },
            "id": "test-where-used",
            "type": "tool_call",
        }],
    )

    result = node({
        "messages": [tool_call],
        "tool_steps": 0,
        "design_change": create_initial_design_change_state(),
        "active_bom_context": {
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
    })

    assert result["active_bom_context"] is None
