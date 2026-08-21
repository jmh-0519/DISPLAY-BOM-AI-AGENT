from langchain_core.messages import AIMessage
from langgraph.graph import END

from agents.bom_agent_state import BomAgentState


MCP_TOOLS = "mcp_tools"
MAX_TOOL_STEPS = 5


def route_agent_response(
    state: BomAgentState,
) -> str:
    """
    Agent Node의 마지막 응답을 확인하여
    MCP Tool Node 실행 또는 Graph 종료를 결정합니다.
    """

    messages = state.get(
        "messages",
        [],
    )

    if not messages:
        raise ValueError(
            "경로 판단에는 하나 이상의 "
            "메시지가 필요합니다."
        )

    last_message = messages[-1]

    if not isinstance(
        last_message,
        AIMessage,
    ):
        raise TypeError(
            "경로 판단의 마지막 메시지는 "
            "AIMessage여야 합니다."
        )

    if last_message.tool_calls:
        current_tool_steps = state.get(
            "tool_steps",
            0,
        )

        if current_tool_steps >= MAX_TOOL_STEPS:
            raise RuntimeError(
                "Agent가 최대 Tool 실행 단계 "
                f"{MAX_TOOL_STEPS}회를 초과했습니다."
            )

        return MCP_TOOLS

    if last_message.content:
        return END

    raise ValueError(
        "Agent 응답에 Tool Call과 "
        "최종 답변이 모두 없습니다."
    )

def route_mcp_tool_result(state: BomAgentState) -> str:
    """Stop immediately after an MCP/business Tool failure.

    Successful Tool observations continue to the Agent for the next ReAct step.
    A failed Tool run is terminal for the current user turn so the same Tool is
    not retried repeatedly with identical arguments.
    """

    if state.get("error"):
        return END
    return "agent"

