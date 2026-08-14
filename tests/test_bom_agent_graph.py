from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agents.bom_agent_graph import (
    BomAgentGraph,
)


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


def make_tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
                "description": "제품 BOM 조회",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "product_id"
                    ],
                },
            },
        }
    ]


def make_design_change_tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "analyze_design_change",
                "description": "설계변경 분석",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
    ]


def test_graph_returns_direct_final_answer():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content="최종 답변입니다.",
            tool_calls=None,
        )
    )

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 업무 규칙",
    )

    result = graph.run(
        "BOM 관리 기준을 알려줘"
    )

    assert result == "최종 답변입니다."

    client.create_agent_completion.assert_called_once()
    mcp_client.call_tool.assert_not_called()


def test_graph_executes_tool_loop():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )
    mcp_client.call_tool.return_value = [
        {
            "product_id": "PRD-001",
            "material_id": "MAT-001",
        }
    ]

    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content=None,
            tool_calls=[
                make_tool_call(
                    tool_call_id="call-001",
                    name="get_bom",
                    arguments=(
                        '{"product_id": "PRD-001"}'
                    ),
                )
            ],
        ),
        make_assistant_message(
            content=(
                "PRD-001의 BOM 조회 결과입니다."
            ),
            tool_calls=None,
        ),
    ]

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = graph.run(
        "PRD-001의 BOM을 조회해줘"
    )

    assert result == (
        "PRD-001의 BOM 조회 결과입니다."
    )

    assert (
        client.create_agent_completion.call_count
        == 2
    )

    mcp_client.call_tool.assert_called_once_with(
        tool_name="get_bom",
        arguments={
            "product_id": "PRD-001"
        },
    )

    second_call = (
        client
        .create_agent_completion
        .call_args_list[1]
        .kwargs
    )

    converted_messages = second_call[
        "messages"
    ]

    assert [
        message["role"]
        for message in converted_messages
    ] == [
        "user",
        "assistant",
        "tool",
    ]

    assert (
        converted_messages[2]
        ["tool_call_id"]
        == "call-001"
    )


def test_graph_rejects_empty_user_input():
    graph = BomAgentGraph(
        client=Mock(),
        mcp_client=Mock(),
        skill_context="BOM 업무 규칙",
    )

    with pytest.raises(
        ValueError,
        match="비어 있지 않은 문자열",
    ):
        graph.run("  ")

def test_graph_remembers_messages_in_same_thread():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content=(
                "LTA400HR01-0의 BOM 조회 결과입니다."
            ),
            tool_calls=None,
        ),
        make_assistant_message(
            content=(
                "앞서 조회한 BOM 중 "
                "DRIVER IC 항목입니다."
            ),
            tool_calls=None,
        ),
    ]

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    graph.run(
        "LTA400HR01-0의 BOM을 보여줘.",
        thread_id="thread-001",
    )

    result = graph.run(
        "그중 DRIVER IC만 알려줘.",
        thread_id="thread-001",
    )

    assert result == (
        "앞서 조회한 BOM 중 "
        "DRIVER IC 항목입니다."
    )

    second_call = (
        client
        .create_agent_completion
        .call_args_list[1]
        .kwargs
    )

    converted_messages = second_call[
        "messages"
    ]

    assert [
        message["role"]
        for message in converted_messages
    ] == [
        "user",
        "assistant",
        "user",
    ]

    assert converted_messages[0]["content"] == (
        "LTA400HR01-0의 BOM을 보여줘"
    )

    assert converted_messages[2]["content"] == (
        "그중 DRIVER IC만 알려줘."
    )        

def test_graph_separates_different_threads():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content="첫 번째 대화 답변",
            tool_calls=None,
        ),
        make_assistant_message(
            content="두 번째 대화 답변",
            tool_calls=None,
        ),
    ]

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    graph.run(
        "첫 번째 대화 질문",
        thread_id="thread-A",
    )

    graph.run(
        "두 번째 대화 질문",
        thread_id="thread-B",
    )

    second_call = (
        client
        .create_agent_completion
        .call_args_list[1]
        .kwargs
    )

    converted_messages = second_call[
        "messages"
    ]

    assert [
        message["role"]
        for message in converted_messages
    ] == [
        "user",
    ]

    assert converted_messages[0]["content"] == (
        "두 번째 대화 질문"
    )


def test_graph_persists_design_change_workflow_state():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = (
        make_design_change_tool_definitions()
    )
    mcp_client.call_tool.return_value = {
        "result": "CONDITIONAL",
        "changeable": True,
    }
    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content=None,
            tool_calls=[
                make_tool_call(
                    tool_call_id="call-analysis",
                    name="analyze_design_change",
                    arguments=(
                        '{"product_id": "PRD-001", '
                        '"old_material_id": "MAT-OLD", '
                        '"new_material_id": "MAT-NEW"}'
                    ),
                )
            ],
        ),
        make_assistant_message(
            content="조건부 승인입니다.",
            tool_calls=None,
        ),
    ]
    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="설계변경 규칙",
    )

    graph.run("설계변경을 분석해줘", thread_id="change-001")
    workflow = graph.get_design_change_state("change-001")

    assert workflow["product_id"] == "PRD-001"
    assert workflow["analysis_status"] == "CONDITIONAL"
    assert workflow["current_step"] == "ANALYSIS_COMPLETED"


def test_graph_returns_initial_workflow_for_new_thread():
    graph = BomAgentGraph(
        client=Mock(),
        mcp_client=Mock(),
        skill_context="설계변경 규칙",
    )

    workflow = graph.get_design_change_state("new-thread")

    assert workflow["analysis_status"] == "NOT_STARTED"
    assert workflow["current_step"] == "NOT_STARTED"
