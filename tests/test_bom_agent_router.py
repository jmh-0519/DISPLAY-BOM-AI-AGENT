import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)
from langgraph.graph import END

from agents.bom_agent_router import (
    MCP_TOOLS,
    route_agent_response,
)


def test_route_to_mcp_tools_when_tool_call_exists():
    state = {
        "messages": [
            HumanMessage(
                content="PRD-001의 BOM을 조회해줘"
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_bom",
                        "args": {
                            "product_id": "PRD-001"
                        },
                        "id": "call-001",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    }

    result = route_agent_response(
        state
    )

    assert result == MCP_TOOLS


def test_route_to_end_when_final_answer_exists():
    state = {
        "messages": [
            AIMessage(
                content="BOM 조회 결과입니다."
            )
        ]
    }

    result = route_agent_response(
        state
    )

    assert result == END


def test_router_rejects_empty_messages():
    with pytest.raises(
        ValueError,
        match="하나 이상의 메시지",
    ):
        route_agent_response({})


def test_router_requires_ai_message():
    state = {
        "messages": [
            HumanMessage(
                content="BOM을 조회해줘"
            )
        ]
    }

    with pytest.raises(
        TypeError,
        match="AIMessage",
    ):
        route_agent_response(
            state
        )


def test_router_rejects_empty_agent_response():
    state = {
        "messages": [
            AIMessage(
                content=""
            )
        ]
    }

    with pytest.raises(
        ValueError,
        match="Tool Call과",
    ):
        route_agent_response(
            state
        )

def test_router_rejects_tool_call_after_max_steps():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_bom",
                        "args": {
                            "product_id": "PRD-001"
                        },
                        "id": "call-006",
                        "type": "tool_call",
                    }
                ],
            )
        ],
        "tool_steps": 5,
    }

    with pytest.raises(
        RuntimeError,
        match="최대 Tool 실행 단계 5회",
    ):
        route_agent_response(
            state
        )        

def test_router_allows_final_answer_after_max_steps():
    state = {
        "messages": [
            AIMessage(
                content="최종 BOM 분석 결과입니다."
            )
        ],
        "tool_steps": 5,
    }

    result = route_agent_response(
        state
    )

    assert result == END        