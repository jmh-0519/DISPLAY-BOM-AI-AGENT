from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_fast_path_nodes import (
    FAST_TOOL_CALL_ID_PREFIX,
    BomFastPathNodes,
    is_graph_fast_tool_result,
)


def test_fast_bom_node_builds_deterministic_get_bom_call():
    node = BomFastPathNodes()
    result = node.bom_read({
        "messages": [HumanMessage(content="LTA400HR01-001 P01 BOM 보여줘")]
    })

    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.tool_calls[0]["name"] == "get_bom"
    assert message.tool_calls[0]["args"] == {
        "plant_code": "P01",
        "product_id": "LTA400HR01-001",
    }
    assert message.tool_calls[0]["id"].startswith(FAST_TOOL_CALL_ID_PREFIX)


def test_fast_where_used_node_builds_deterministic_tool_call():
    node = BomFastPathNodes()
    result = node.where_used({
        "messages": [HumanMessage(content="P01에서 0001-310901 포함한 모델 알려줘")]
    })

    message = result["messages"][0]
    assert message.tool_calls[0]["name"] == "get_bom_where_used"
    assert message.tool_calls[0]["args"] == {
        "plant_code": "P01",
        "item_code": "0001-310901",
    }


def test_graph_fast_tool_result_is_identified_by_call_id():
    state = {
        "messages": [ToolMessage(
            content="[]",
            tool_call_id=f"{FAST_TOOL_CALL_ID_PREFIX}bom-123",
            name="get_bom",
        )]
    }
    assert is_graph_fast_tool_result(state) is True


def test_fast_finalize_returns_ai_message_without_llm():
    result = BomFastPathNodes().finalize_read({
        "messages": [ToolMessage(
            content="[]",
            tool_call_id=f"{FAST_TOOL_CALL_ID_PREFIX}bom-123",
            name="get_bom",
        )]
    })
    assert result["messages"][0].content == "BOM 조회 결과를 확인해 주세요."
