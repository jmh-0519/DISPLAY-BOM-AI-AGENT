from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from agents.bom_agent_node import BomAgentNode


def make_assistant_message(
    content=None,
    tool_calls=None,
):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )


def make_tool_call(
    tool_call_id,
    name,
    arguments,
):
    return SimpleNamespace(
        id=tool_call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def test_agent_node_returns_final_ai_message():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
            },
        }
    ]

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content="조회 결과입니다.",
            tool_calls=None,
        )
    )

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = node(
        {
            "messages": [
                HumanMessage(
                    content="PRD-001의 BOM을 조회해줘"
                )
            ]
        }
    )

    assert len(result["messages"]) == 1
    assert isinstance(
        result["messages"][0],
        AIMessage,
    )
    assert (
        result["messages"][0].content
        == "조회 결과입니다."
    )
    assert result["messages"][0].tool_calls == []
    assert result["error"] is None

    client.create_agent_completion.assert_called_once()


def test_agent_node_converts_tool_call():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
            },
        }
    ]

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content=None,
            tool_calls=[
                make_tool_call(
                    tool_call_id="call-001",
                    name="get_bom",
                    arguments='{"product_code": "PRD-001"}',
                )
            ],
        )
    )

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = node(
        {
            "messages": [
                HumanMessage(
                    content="PRD-001의 BOM을 조회해줘"
                )
            ]
        }
    )

    ai_message = result["messages"][0]

    assert ai_message.content == ""
    assert len(ai_message.tool_calls) == 1
    assert (
        ai_message.tool_calls[0]["name"]
        == "get_bom"
    )
    assert ai_message.tool_calls[0]["args"] == {
        "product_code": "PRD-001"
    }
    assert (
        ai_message.tool_calls[0]["id"]
        == "call-001"
    )


def test_agent_node_converts_message_history():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
            },
        }
    ]

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content="최종 답변",
            tool_calls=None,
        )
    )

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    node(
        {
            "messages": [
                HumanMessage(
                    content="BOM을 조회해줘"
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_bom",
                            "args": {
                                "product_code": "PRD-001"
                            },
                            "id": "call-001",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content='{"product_code":"PRD-001"}',
                    tool_call_id="call-001",
                    name="get_bom",
                ),
            ]
        }
    )

    call_arguments = (
        client
        .create_agent_completion
        .call_args
        .kwargs
    )

    converted_messages = (
        call_arguments["messages"]
    )

    assert converted_messages[0]["role"] == "user"
    assert (
        converted_messages[1]["role"]
        == "assistant"
    )
    assert (
        converted_messages[1]
        ["tool_calls"][0]
        ["function"]["name"]
        == "get_bom"
    )
    assert converted_messages[2]["role"] == "tool"
    assert (
        converted_messages[2]["tool_call_id"]
        == "call-001"
    )


def test_agent_node_rejects_empty_messages():
    node = BomAgentNode(
        client=Mock(),
        mcp_client=Mock(),
        skill_context="BOM 조회 규칙",
    )

    with pytest.raises(
        ValueError,
        match="하나 이상의 메시지",
    ):
        node({})