from types import SimpleNamespace
from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode


def test_prompt_budget_instrumentation_does_not_require_real_azure_client():
    client = Mock()
    client.create_agent_completion.return_value = SimpleNamespace(
        content="최종 답변",
        tool_calls=None,
    )
    mcp = Mock()
    mcp.get_tool_definitions.return_value = [{
        "type": "function",
        "function": {
            "name": "get_bom",
            "description": "BOM",
            "parameters": {"type": "object", "properties": {}},
        },
    }]

    node = BomAgentNode(client, mcp, "테스트 Skill")
    result = node({
        "messages": [HumanMessage(content="업무 기준을 설명해줘")],
    })

    assert result["messages"][0].content == "최종 답변"
    client.create_agent_completion.assert_called_once()
