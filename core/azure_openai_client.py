from typing import Any

from openai import AzureOpenAI
from openai.types.chat import (
    ChatCompletionMessage,
)

from core.settings import Settings
from core.observability import (
    LangfuseObservability,
    get_observability,
    summarize_messages,
    summarize_value,
)
from core.performance_profiler import (
    performance_span,
    record_performance_event,
)


class AzureOpenAIClient:
    """
    Azure OpenAI Gateway와 통신하는 Client입니다.

    책임:
    - Azure OpenAI 인증
    - 일반 Chat Completion
    - Tool Calling
    - Multi-step Agent Completion
    - 최종 자연어 응답 생성

    BOM 업무 판단이나 Tool 실행 자체는
    이 클래스에서 수행하지 않습니다.
    """

    def __init__(
        self,
        settings: Settings,
        observability: LangfuseObservability | None = None,
    ) -> None:
        self.settings = settings
        self.observability = observability or get_observability()

        self.client = AzureOpenAI(
            azure_endpoint=(
                settings.azure_openai_endpoint
            ),
            api_key=(
                settings.azure_openai_api_key
            ),
            api_version=(
                settings.azure_openai_api_version
            ),
        )

    def _create_completion(self, **request: Any) -> Any:
        messages = request.get("messages") or []
        with self.observability.observe(
            "azure-openai.chat-completion",
            as_type="generation",
            input_summary=summarize_messages(messages),
            metadata={
                "tool_definition_count": len(request.get("tools") or []),
                "temperature": request.get("temperature"),
            },
            model=self.settings.azure_openai_deployment,
        ) as generation:
            prompt_chars = sum(
                len(str(message.get("content") or ""))
                for message in messages
            )
            with performance_span(
                "llm",
                "azure_openai.chat_completion",
                metadata={
                    "message_count": len(messages),
                    "tool_definition_count": len(request.get("tools") or []),
                    "prompt_chars": prompt_chars,
                },
            ):
                response = self.client.chat.completions.create(**request)
            usage = getattr(response, "usage", None)
            usage_details = None
            if usage is not None:
                usage_details = {
                    "input": int(getattr(usage, "prompt_tokens", 0) or 0),
                    "output": int(getattr(usage, "completion_tokens", 0) or 0),
                    "total": int(getattr(usage, "total_tokens", 0) or 0),
                }
            if usage_details:
                record_performance_event(
                    category="llm",
                    name="azure_openai.usage",
                    metadata={
                        "message_count": len(messages),
                        "tool_definition_count": len(request.get("tools") or []),
                    },
                    metrics=usage_details,
                )

            message = response.choices[0].message
            generation.finish(
                output=summarize_value({
                    "has_content": bool(message.content),
                    "tool_call_count": len(message.tool_calls or []),
                }),
                usage_details=usage_details,
            )
            return response

    # =========================================================
    # 공통 System Prompt
    # =========================================================

    @staticmethod
    def _build_agent_system_prompt(
        skill_context: str | None = None,
    ) -> str:
        """
        Agent Tool Calling에서 사용할
        System Prompt를 생성합니다.
        """

        system_content = (
            "당신은 Display BOM AI Agent입니다. "
            "사용자의 요청을 처리하는 데 "
            "적절한 Tool이 있으면 해당 Tool을 사용하세요. "
            "BOM, 제품, 자재 데이터를 추측하지 마세요. "
            "반드시 Tool 실행 결과를 근거로 판단하세요. "
            "업무가 완료되기 전에 추가 Tool 호출이 "
            "필요하다면 최종 답변을 생성하지 말고 "
            "다음 Tool을 호출하세요."
        )

        if (
            isinstance(
                skill_context,
                str,
            )
            and skill_context.strip()
        ):
            system_content += (
                "\n\n"
                "다음은 현재 업무에 적용할 Skill입니다. "
                "Skill에 정의된 업무 절차, 판단 규칙, "
                "제약사항을 따르세요.\n\n"
                f"{skill_context.strip()}"
            )

        return system_content

    # =========================================================
    # 일반 Chat
    # =========================================================

    def create_chat_completion(
        self,
        user_message: str,
    ) -> str:
        """
        일반 사용자 메시지를 Azure OpenAI에 전달합니다.
        """

        if (
            not isinstance(
                user_message,
                str,
            )
            or not user_message.strip()
        ):
            raise ValueError(
                "user_message는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        response = (
            self._create_completion(
                model=(
                    self.settings
                    .azure_openai_deployment
                ),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 Display BOM AI Agent "
                            "개발을 지원하는 "
                            "어시스턴트입니다. "
                            "답변은 한국어로 "
                            "간결하게 작성하세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            user_message.strip()
                        ),
                    },
                ],
                temperature=0,
            )
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if not content:
            raise ValueError(
                "Azure OpenAI에서 "
                "응답 내용을 반환하지 않았습니다."
            )

        return content

    # =========================================================
    # 기존 1회 Tool Calling
    # =========================================================

    def create_tool_call_completion(
        self,
        user_message: str,
        tools: list[dict[str, Any]],
        skill_context: str | None = None,
    ) -> ChatCompletionMessage:
        """
        기존 1회 Tool Calling 인터페이스입니다.

        기존 테스트와 코드 호환을 위해 유지합니다.
        """

        if (
            not isinstance(
                user_message,
                str,
            )
            or not user_message.strip()
        ):
            raise ValueError(
                "user_message는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        if (
            not isinstance(
                tools,
                list,
            )
            or not tools
        ):
            raise ValueError(
                "tools는 하나 이상의 "
                "Tool 정의를 포함해야 합니다."
            )

        system_content = (
            self._build_agent_system_prompt(
                skill_context
            )
        )

        response = (
            self._create_completion(
                model=(
                    self.settings
                    .azure_openai_deployment
                ),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            system_content
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            user_message.strip()
                        ),
                    },
                ],
                tools=tools,
                tool_choice="auto",
                temperature=0,
            )
        )

        return (
            response
            .choices[0]
            .message
        )

    # =========================================================
    # 신규 Multi-step Agent Completion
    # =========================================================

    def create_agent_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        skill_context: str | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> ChatCompletionMessage:
        """
        Multi-step Agent Loop에서 사용합니다.

        이전 Assistant Tool Call과 Tool 실행 결과를 포함한
        전체 messages를 받아 다음 행동을 판단합니다.

        모델은:
        - 추가 Tool을 호출하거나
        - 업무가 완료되면 최종 자연어 응답을 반환합니다.
        """

        if (
            not isinstance(
                messages,
                list,
            )
            or not messages
        ):
            raise ValueError(
                "messages는 하나 이상의 "
                "대화 메시지를 포함해야 합니다."
            )

        if not isinstance(tools, list):
            raise ValueError(
                "tools는 Tool 정의 list여야 합니다."
            )

        system_content = (
            self._build_agent_system_prompt(
                skill_context
            )
        )

        request_messages = [
            {
                "role": "system",
                "content": system_content,
            }
        ]

        request_messages.extend(
            messages
        )

        request: dict[str, Any] = {
            "model": self.settings.azure_openai_deployment,
            "messages": request_messages,
            "temperature": 0,
        }

        record_performance_event(
            category="prompt",
            name="llm.system_prompt_budget",
            metrics={
                "system_prompt_chars": len(system_content),
                "request_message_count": len(request_messages),
            },
        )

        # STEP31: Explain Tool 실행 후 최종 자연어 답변만 생성해야 하는
        # 턴에서는 허용 Tool이 0개일 수 있습니다. 이 경우 Azure OpenAI에
        # tools/tool_choice 자체를 보내지 않아 모델의 반복 Tool 호출을 막습니다.
        if tools:
            request["tools"] = tools
            request["tool_choice"] = (
                {"type": "function", "function": {"name": tool_choice}}
                if isinstance(tool_choice, str) and tool_choice != "auto"
                else tool_choice
            )

        response = self._create_completion(**request)

        return (
            response
            .choices[0]
            .message
        )

    # =========================================================
    # SPEED2F1 Dedicated Analysis Finalizer
    # =========================================================

    def create_analysis_final_answer(
        self,
        *,
        user_message: str,
        analysis_evidence: str,
    ) -> str:
        """Explain completed Design Change Analysis evidence without Agent baggage.

        This call intentionally sends:
        - no Skill context
        - no Runtime Gate
        - no Tool definitions
        - no previous conversation history

        Business authority remains in the deterministic Tool/Service result.
        The LLM only converts verified evidence into concise Korean prose.
        """

        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("user_message는 비어 있지 않은 문자열이어야 합니다.")
        if not isinstance(analysis_evidence, str) or not analysis_evidence.strip():
            raise ValueError("analysis_evidence는 비어 있지 않은 문자열이어야 합니다.")

        system_content = (
            "당신은 Display BOM 설계변경 분석 결과 설명자입니다. "
            "반드시 제공된 Analysis Evidence만 근거로 한국어로 간결하게 답하세요. "
            "후보, 상태, 수량, 사유, 점수, 공급/재고 정보는 Evidence에 있는 값만 사용하세요. "
            "Evidence에 없는 후보나 사유를 만들거나 추측하지 마세요. "
            "PASS/CONDITIONAL/FAIL을 구분하고 주요 판단 이유를 설명하세요. "
            "후보 순서를 임의로 바꾸지 말고, Evidence가 추천이라고 명시하지 않았다면 "
            "임의로 최종 추천 또는 승인으로 표현하지 마세요. "
            "Analysis는 설계변경 Request 생성이나 Production E-BOM Apply가 아님을 유지하세요. "
            "사용자가 다음 단계에서 후보 확인·재검증·진행 여부를 결정할 수 있음을 필요할 때만 안내하세요."
        )

        user_content = (
            f"사용자 요청:\n{user_message.strip()}\n\n"
            "Analysis Evidence(JSON):\n"
            f"{analysis_evidence.strip()}"
        )

        # Keep SPEED2F0 prompt-budget reporting comparable. This is the same
        # metric schema as the full Agent call, but Skill/Runtime/Tools are zero.
        message_payload_chars = len(user_content)
        approx_total_chars = len(system_content) + message_payload_chars

        record_performance_event(
            category="prompt",
            name="llm.prompt_budget",
            metadata={
                "message_count": 1,
                "tool_definition_count": 0,
                "finalizer": True,
            },
            metrics={
                "core_system_chars": len(system_content),
                "skill_wrapper_chars": 0,
                "base_skill_chars": 0,
                "runtime_gate_chars": 0,
                "message_payload_chars": message_payload_chars,
                "human_content_chars": message_payload_chars,
                "assistant_content_chars": 0,
                "tool_content_chars": 0,
                "tool_definition_chars": 0,
                "tool_definition_count": 0,
                "approx_total_chars": approx_total_chars,
            },
        )
        record_performance_event(
            category="prompt",
            name="llm.system_prompt_budget",
            metadata={"finalizer": True},
            metrics={
                "system_prompt_chars": len(system_content),
                "request_message_count": 2,
            },
        )

        response = self._create_completion(
            model=self.settings.azure_openai_deployment,
            messages=[
                {
                    "role": "system",
                    "content": system_content,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            temperature=0,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Azure OpenAI에서 Analysis 최종 답변을 반환하지 않았습니다.")
        return str(content).strip()

    # =========================================================
    # 기존 Final Answer
    # =========================================================

    def create_final_answer(
        self,
        user_message: str,
        assistant_message: ChatCompletionMessage,
        tool_call_id: str,
        tool_name: str,
        tool_result: str,
    ) -> str:
        """
        기존 1회 Tool Calling 구조의 최종 답변 생성 메서드입니다.

        Multi-step Agent 전환 완료 후
        제거 여부를 판단합니다.
        """

        if (
            not isinstance(
                user_message,
                str,
            )
            or not user_message.strip()
        ):
            raise ValueError(
                "user_message는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        if not tool_call_id:
            raise ValueError(
                "tool_call_id가 필요합니다."
            )

        if not tool_name:
            raise ValueError(
                "tool_name이 필요합니다."
            )

        if (
            not isinstance(
                tool_result,
                str,
            )
            or not tool_result.strip()
        ):
            raise ValueError(
                "tool_result는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        response = (
            self._create_completion(
                model=(
                    self.settings
                    .azure_openai_deployment
                ),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 Display BOM AI Agent입니다. "
                            "반드시 Tool 실행 결과만 "
                            "근거로 답변하세요. "
                            "조회되지 않은 데이터는 "
                            "추측하거나 생성하지 마세요. "
                            "결과를 사용자가 이해하기 쉬운 "
                            "한국어로 정리하세요. "
                            "상태가 CONDITIONAL이거나 "
                            "비정상인 항목은 "
                            "별도로 알려주세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            user_message.strip()
                        ),
                    },
                    assistant_message.model_dump(
                        exclude_none=True
                    ),
                    {
                        "role": "tool",
                        "tool_call_id": (
                            tool_call_id
                        ),
                        "name": tool_name,
                        "content": tool_result,
                    },
                ],
                temperature=0,
            )
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if not content:
            raise ValueError(
                "Azure OpenAI에서 "
                "최종 답변을 반환하지 않았습니다."
            )

        return content
