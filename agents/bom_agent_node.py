import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from agents.bom_agent_state import BomAgentState
from core.azure_openai_client import AzureOpenAIClient
from mcp_client.client import DisplayBomMcpClient


class BomAgentNode:
    """
    LangGraph에서 Azure OpenAI의
    다음 행동을 한 번 판단하는 Agent Node입니다.

    Tool을 직접 실행하지 않습니다.
    """

    def __init__(
        self,
        client: AzureOpenAIClient,
        mcp_client: DisplayBomMcpClient,
        skill_context: str,
    ) -> None:
        self.client = client
        self.mcp_client = mcp_client
        self.skill_context = skill_context

    def __call__(
        self,
        state: BomAgentState,
    ) -> BomAgentState:
        messages = state.get(
            "messages",
            [],
        )

        if not messages:
            raise ValueError(
                "Agent Node 실행에는 "
                "하나 이상의 메시지가 필요합니다."
            )

        openai_messages = (
            self._convert_messages(
                messages
            )
        )

        tool_definitions = (
            self.mcp_client
            .get_tool_definitions()
        )

        assistant_message = (
            self.client
            .create_agent_completion(
                messages=openai_messages,
                tools=tool_definitions,
                skill_context=(
                    self.skill_context
                ),
            )
        )

        ai_message = (
            self._convert_assistant_message(
                assistant_message
            )
        )

        return {
            "messages": [ai_message],
            "error": None,
        }

    @staticmethod
    def _convert_messages(
        messages: list[BaseMessage],
    ) -> list[dict[str, Any]]:
        """
        LangChain 메시지를 Azure OpenAI가 받는
        dictionary 메시지로 변환합니다.
        """

        converted_messages: list[
            dict[str, Any]
        ] = []

        for message in messages:
            if isinstance(
                message,
                HumanMessage,
            ):
                converted_messages.append(
                    {
                        "role": "user",
                        "content": message.content,
                    }
                )
                continue

            if isinstance(
                message,
                AIMessage,
            ):
                assistant_data: dict[
                    str,
                    Any,
                ] = {
                    "role": "assistant",
                    "content": (
                        message.content or None
                    ),
                }

                if message.tool_calls:
                    assistant_data["tool_calls"] = [
                        {
                            "id": tool_call["id"],
                            "type": "function",
                            "function": {
                                "name": (
                                    tool_call["name"]
                                ),
                                "arguments": json.dumps(
                                    tool_call["args"],
                                    ensure_ascii=False,
                                ),
                            },
                        }
                        for tool_call
                        in message.tool_calls
                    ]

                converted_messages.append(
                    assistant_data
                )
                continue

            if isinstance(
                message,
                ToolMessage,
            ):
                tool_data: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": (
                        message.tool_call_id
                    ),
                    "content": message.content,
                }

                if message.name:
                    tool_data["name"] = (
                        message.name
                    )

                converted_messages.append(
                    tool_data
                )
                continue

            raise TypeError(
                "지원하지 않는 메시지 타입입니다: "
                f"{type(message).__name__}"
            )

        return converted_messages

    @staticmethod
    def _convert_assistant_message(
        assistant_message: Any,
    ) -> AIMessage:
        """
        Azure OpenAI의 ChatCompletionMessage를
        LangChain AIMessage로 변환합니다.
        """

        tool_calls = []

        for tool_call in (
            assistant_message.tool_calls or []
        ):
            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except json.JSONDecodeError as error:
                raise ValueError(
                    "Azure OpenAI가 올바르지 않은 "
                    "Tool arguments를 반환했습니다."
                ) from error

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    "Tool arguments는 "
                    "JSON 객체여야 합니다."
                )

            tool_calls.append(
                {
                    "name": (
                        tool_call.function.name
                    ),
                    "args": arguments,
                    "id": tool_call.id,
                    "type": "tool_call",
                }
            )

        return AIMessage(
            content=(
                assistant_message.content or ""
            ),
            tool_calls=tool_calls,
        )