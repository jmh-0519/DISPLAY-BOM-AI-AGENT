from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode
from mcp_client.client import DisplayBomMcpClient


def _node():
    client = MagicMock()
    mcp_client = MagicMock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom", "description": "", "parameters": {}}},
        {"type": "function", "function": {"name": "get_bom_where_used", "description": "", "parameters": {}}},
        {"type": "function", "function": {"name": "list_plants", "description": "", "parameters": {}}},
    ]
    return BomAgentNode(client, mcp_client, "skill"), client, mcp_client


def test_simple_greeting_uses_no_llm():
    node, client, _ = _node()
    result = node({"messages": [HumanMessage(content="안녕하세요")], "user_query": "안녕하세요"})
    assert "Display BOM AI Agent" in result["messages"][0].content
    client.create_agent_completion.assert_not_called()


def test_plain_bom_query_builds_direct_tool_call_without_llm():
    node, client, _ = _node()
    query = "LTA400HR01-001 P01 BOM 보여줘"
    result = node({"messages": [HumanMessage(content=query)], "user_query": query})
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "get_bom"
    assert call["args"]["plant_code"] == "P01"
    assert call["args"]["product_id"] == "LTA400HR01-001"
    client.create_agent_completion.assert_not_called()


def test_where_used_observation_skips_final_llm():
    node, client, _ = _node()
    query = "P01에서 0001-310901 포함한 모델 알려줘"
    result = node({
        "messages": [
            HumanMessage(content=query),
            ToolMessage(content='{"item_code":"0001-310901"}', tool_call_id="x", name="get_bom_where_used"),
        ],
        "user_query": query,
    })
    assert "역방향 BOM" in result["messages"][0].content
    client.create_agent_completion.assert_not_called()


def test_tool_definition_cache_returns_copy(monkeypatch):
    DisplayBomMcpClient.clear_tool_definition_cache()
    client = DisplayBomMcpClient.__new__(DisplayBomMcpClient)
    calls = {"count": 0}

    async def fake_defs():
        calls["count"] += 1
        return [{"type": "function", "function": {"name": "get_bom"}}]

    monkeypatch.setattr(client, "_get_tool_definitions_async", fake_defs)
    first = client.get_tool_definitions()
    second = client.get_tool_definitions()
    first.append({"mutated": True})
    assert calls["count"] == 1
    assert len(second) == 1
    DisplayBomMcpClient.clear_tool_definition_cache()
