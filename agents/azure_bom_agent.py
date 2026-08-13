import json
from typing import Any

from core.azure_openai_client import (
    AzureOpenAIClient,
)
from mcp_client.client import (
    DisplayBomMcpClient,
)


class AzureBomAgent:
    """
    Azure OpenAI, Skill, MCP를 이용하여
    Display BOM 업무 요청을 처리하는 Agent입니다.

    처리 과정:
    1. 사용자 질문 정규화
    2. MCP Server에서 Tool 목록 조회
    3. Skill과 함께 Azure OpenAI에 전달
    4. 모델이 필요한 Tool 선택
    5. MCP Tool 실행
    6. Tool 결과를 대화 이력에 추가
    7. Azure OpenAI가 다음 행동을 다시 판단
    8. 업무가 완료되면 최종 답변 반환
    """

    MAX_TOOL_STEPS = 5

    def __init__(
        self,
        client: AzureOpenAIClient,
        mcp_client: DisplayBomMcpClient,
        skill_context: str,
    ) -> None:
        self.client = client
        self.mcp_client = mcp_client
        self.skill_context = skill_context

    def run(
        self,
        user_input: str,
    ) -> str:
        """
        사용자의 자연어 질문을
        Multi-step Tool Loop로 처리합니다.
        """

        normalized_input = (
            self._normalize_input(
                user_input
            )
        )

        tool_definitions = (
            self.mcp_client
            .get_tool_definitions()
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": normalized_input,
            }
        ]

        for _ in range(
            self.MAX_TOOL_STEPS
        ):
            assistant_message = (
                self.client
                .create_agent_completion(
                    messages=messages,
                    tools=tool_definitions,
                    skill_context=(
                        self.skill_context
                    ),
                )
            )

            # ---------------------------------------------
            # Tool Call이 없으면 업무 완료
            # ---------------------------------------------

            if not assistant_message.tool_calls:
                if assistant_message.content:
                    return (
                        assistant_message
                        .content
                    )

                raise ValueError(
                    "Azure OpenAI가 Tool 호출 또는 "
                    "최종 답변을 반환하지 않았습니다."
                )

            # ---------------------------------------------
            # Assistant Tool Call 메시지 저장
            # ---------------------------------------------

            messages.append(
                assistant_message.model_dump(
                    exclude_none=True
                )
            )

            # ---------------------------------------------
            # 요청된 MCP Tool 실행
            # ---------------------------------------------

            for tool_call in (
                assistant_message.tool_calls
            ):
                tool_name = (
                    tool_call.function.name
                )

                arguments = (
                    self._parse_arguments(
                        tool_call
                        .function
                        .arguments
                    )
                )

                tool_result = (
                    self.mcp_client
                    .call_tool(
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                )

                serialized_result = (
                    self._serialize_tool_result(
                        tool_result
                    )
                )

                # -----------------------------------------
                # Tool Observation을 대화 이력에 추가
                # -----------------------------------------

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "name": tool_name,
                        "content": (
                            serialized_result
                        ),
                    }
                )

        raise RuntimeError(
            "Agent가 최대 Tool 실행 단계 "
            f"{self.MAX_TOOL_STEPS}회를 초과했습니다."
        )

    @staticmethod
    def _normalize_input(
        user_input: str,
    ) -> str:
        """
        사용자 입력을 검증하고
        공백을 정리합니다.
        """

        if (
            not isinstance(
                user_input,
                str,
            )
            or not user_input.strip()
        ):
            raise ValueError(
                "질문은 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        return " ".join(
            user_input
            .strip()
            .split()
        )

    @staticmethod
    def _parse_arguments(
        raw_arguments: str,
    ) -> dict[str, Any]:
        """
        Azure OpenAI가 생성한 JSON 문자열을
        dictionary로 변환합니다.
        """

        try:
            arguments = json.loads(
                raw_arguments
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

        return arguments

    @staticmethod
    def _serialize_tool_result(
        data: Any,
    ) -> str:
        """
        MCP Tool 실행 결과를
        Azure OpenAI 메시지용 문자열로 변환합니다.
        """

        if hasattr(
            data,
            "to_json",
        ):
            return data.to_json(
                orient="records",
                force_ascii=False,
            )

        return json.dumps(
            data,
            ensure_ascii=False,
            default=str,
        )