from typing import Any
from unittest.mock import Mock

import pytest
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_message_tool_call import (
    Function,
)

from agents.azure_bom_agent import AzureBomAgent


SAMPLE_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_product",
            "description": "제품을 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                    },
                },
                "required": [
                    "keyword",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bom",
            "description": "제품 BOM을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                    },
                },
                "required": [
                    "product_id",
                ],
            },
        },
    },
]


def create_tool_message(
    tool_name: str,
    arguments: str,
    call_id: str,
) -> ChatCompletionMessage:
    """
    Tool Call이 포함된 테스트용
    Assistant Message를 생성합니다.
    """

    tool_call = ChatCompletionMessageToolCall(
        id=call_id,
        type="function",
        function=Function(
            name=tool_name,
            arguments=arguments,
        ),
    )

    return ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[
            tool_call,
        ],
    )


def create_final_message(
    content: str,
) -> ChatCompletionMessage:
    """
    Tool Call 없이 최종 답변을 반환하는
    Assistant Message를 생성합니다.
    """

    return ChatCompletionMessage(
        role="assistant",
        content=content,
        tool_calls=None,
    )


def create_agent(
    client: Mock,
    mcp_client: Mock | None = None,
) -> AzureBomAgent:

    if mcp_client is None:
        mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        SAMPLE_TOOL_DEFINITIONS
    )

    return AzureBomAgent(
        client=client,
        mcp_client=mcp_client,
        skill_context=(
            "# BOM Query Skill\n"
            "제품 ID가 불명확하면 제품을 검색한 후 "
            "BOM을 조회한다."
        ),
    )


def test_agent_executes_single_tool() -> None:
    """
    제품 ID가 명확한 경우:
    get_bom -> 최종 답변
    """

    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        SAMPLE_TOOL_DEFINITIONS
    )

    mcp_client.call_tool.return_value = [
        {
            "product_id": "LTA400HR01-0",
            "material_id": "MAT-001",
        }
    ]

    client.create_agent_completion.side_effect = [
        create_tool_message(
            tool_name="get_bom",
            arguments=(
                '{"product_id":"LTA400HR01-0"}'
            ),
            call_id="call-bom-001",
        ),
        create_final_message(
            "LTA400HR01-0의 BOM을 조회했습니다."
        ),
    ]

    agent = create_agent(
        client,
        mcp_client,
    )

    result = agent.run(
        "LTA400HR01-0의 BOM을 보여줘"
    )

    assert (
        result
        == "LTA400HR01-0의 BOM을 조회했습니다."
    )

    mcp_client.call_tool.assert_called_once_with(
        tool_name="get_bom",
        arguments={
            "product_id": "LTA400HR01-0",
        },
    )

    assert (
        client
        .create_agent_completion
        .call_count
        == 2
    )


def test_agent_executes_multi_step_tools() -> None:
    """
    제품 ID가 불명확한 경우:

    search_product
        ->
    get_bom
        ->
    최종 답변
    """

    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        SAMPLE_TOOL_DEFINITIONS
    )

    mcp_client.call_tool.side_effect = [
        [
            {
                "product_id": "LTA400HR01-0",
                "product_name": (
                    "40IN FHD 60HZ LCD MODEL"
                ),
            }
        ],
        [
            {
                "root_model": "LTA400HR01-0",
                "bom_child": "MAT-001",
                "quantity": 1,
            }
        ],
    ]

    client.create_agent_completion.side_effect = [
        create_tool_message(
            tool_name="search_product",
            arguments=(
                '{"keyword":"40IN FHD 60HZ LCD MODEL"}'
            ),
            call_id="call-search-001",
        ),
        create_tool_message(
            tool_name="get_bom",
            arguments=(
                '{"product_id":"LTA400HR01-0"}'
            ),
            call_id="call-bom-001",
        ),
        create_final_message(
            "40인치 FHD 60Hz LCD 모델의 "
            "BOM을 조회했습니다."
        ),
    ]

    agent = create_agent(
        client,
        mcp_client,
    )

    result = agent.run(
        "40인치 FHD 60Hz LCD 모델의 "
        "BOM을 보여줘"
    )

    assert (
        result
        == "40인치 FHD 60Hz LCD 모델의 "
        "BOM을 조회했습니다."
    )

    assert (
        mcp_client.call_tool.call_count
        == 2
    )

    first_call = (
        mcp_client
        .call_tool
        .call_args_list[0]
    )

    assert (
        first_call.kwargs["tool_name"]
        == "search_product"
    )

    second_call = (
        mcp_client
        .call_tool
        .call_args_list[1]
    )

    assert (
        second_call.kwargs["tool_name"]
        == "get_bom"
    )

    assert (
        second_call.kwargs["arguments"]
        == {
            "product_id": "LTA400HR01-0",
        }
    )

    assert (
        client
        .create_agent_completion
        .call_count
        == 3
    )


def test_agent_passes_skill_context() -> None:
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        SAMPLE_TOOL_DEFINITIONS
    )

    client.create_agent_completion.return_value = (
        create_final_message(
            "안녕하세요."
        )
    )

    agent = create_agent(
        client,
        mcp_client,
    )

    agent.run(
        "안녕하세요"
    )

    call_kwargs = (
        client
        .create_agent_completion
        .call_args
        .kwargs
    )

    assert (
        "# BOM Query Skill"
        in call_kwargs["skill_context"]
    )


@pytest.mark.parametrize(
    "user_input",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_agent_rejects_invalid_input(
    user_input: Any,
) -> None:

    client = Mock()

    agent = create_agent(
        client
    )

    with pytest.raises(
        ValueError
    ):
        agent.run(
            user_input
        )


def test_agent_rejects_invalid_arguments() -> None:
    client = Mock()

    client.create_agent_completion.return_value = (
        create_tool_message(
            tool_name="get_bom",
            arguments="{invalid-json}",
            call_id="call-invalid-001",
        )
    )

    agent = create_agent(
        client
    )

    with pytest.raises(
        ValueError,
        match="Tool arguments",
    ):
        agent.run(
            "BOM을 보여줘"
        )


def test_agent_returns_text_without_tool() -> None:
    client = Mock()

    client.create_agent_completion.return_value = (
        create_final_message(
            "BOM 관련 질문을 입력해 주세요."
        )
    )

    agent = create_agent(
        client
    )

    result = agent.run(
        "안녕하세요"
    )

    assert (
        result
        == "BOM 관련 질문을 입력해 주세요."
    )


def test_agent_stops_after_max_steps() -> None:
    """
    LLM이 계속 Tool만 호출하는 경우
    무한 Loop를 방지하는지 확인합니다.
    """

    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        SAMPLE_TOOL_DEFINITIONS
    )

    mcp_client.call_tool.return_value = []

    client.create_agent_completion.side_effect = [
        create_tool_message(
            tool_name="search_product",
            arguments='{"keyword":"LCD"}',
            call_id=f"call-{index}",
        )
        for index in range(
            AzureBomAgent.MAX_TOOL_STEPS
        )
    ]

    agent = create_agent(
        client,
        mcp_client,
    )

    with pytest.raises(
        RuntimeError,
        match="최대 Tool 실행 단계",
    ):
        agent.run(
            "LCD 제품을 계속 찾아줘"
        )

    assert (
        mcp_client.call_tool.call_count
        == AzureBomAgent.MAX_TOOL_STEPS
    )