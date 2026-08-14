from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
import base64
import json
import re
from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from agents.bom_agent_node import BomAgentNode
from agents.bom_agent_router import (
    MCP_TOOLS,
    route_agent_response,
)
from agents.bom_agent_state import BomAgentState
from agents.design_change_workflow_state import (
    create_initial_design_change_state,
)
from agents.bom_mcp_tool_node import (
    BomMcpToolNode,
)
from core.azure_openai_client import (
    AzureOpenAIClient,
)
from mcp_client.client import (
    DisplayBomMcpClient,
)
from core.observability import (
    LangfuseObservability,
    get_observability,
    summarize_text,
    summarize_value,
)

from langgraph.checkpoint.memory import InMemorySaver

AGENT = "agent"


class BomAgentGraph:
    """
    Display BOM AI Agent의 LangGraph 실행 흐름입니다.

    START
      → Agent Node
        → MCP Tool Node → Agent Node
        → END
    """

    def __init__(
        self,
        client: AzureOpenAIClient,
        mcp_client: DisplayBomMcpClient,
        skill_context: str,
        checkpointer=None,
        observability: LangfuseObservability | None = None,
    ) -> None:
        self.observability = observability or get_observability()
        self.agent_node = BomAgentNode(
            client=client,
            mcp_client=mcp_client,
            skill_context=skill_context,
        )

        self.mcp_tool_node = BomMcpToolNode(
            mcp_client=mcp_client,
            observability=self.observability,
        )

        self.checkpointer = (
            checkpointer
            if checkpointer is not None
            else InMemorySaver()
        )

        self.graph = self._build_graph()

    def _build_graph(self):
        """
        Agent와 MCP Tool Node를 연결하고
        실행 가능한 Graph로 컴파일합니다.
        """

        workflow = StateGraph(
            BomAgentState
        )

        workflow.add_node(
            AGENT,
            self._observed_node(AGENT, self.agent_node),
        )
        workflow.add_node(
            MCP_TOOLS,
            self._observed_node(MCP_TOOLS, self.mcp_tool_node),
        )

        workflow.add_edge(
            START,
            AGENT,
        )

        workflow.add_conditional_edges(
            AGENT,
            route_agent_response,
            {
                MCP_TOOLS: MCP_TOOLS,
                END: END,
            },
        )

        workflow.add_edge(
            MCP_TOOLS,
            AGENT,
        )

        return workflow.compile(
            checkpointer=self.checkpointer
        )

    def _observed_node(self, name, node):
        def invoke_node(state):
            messages = state.get("messages", [])
            with self.observability.observe(
                f"langgraph.{name}",
                input_summary={
                    "message_count": len(messages),
                    "tool_steps": state.get("tool_steps", 0),
                },
                metadata={"node": name},
            ) as span:
                result = node(state)
                span.finish(output=summarize_value(result))
                return result

        return invoke_node

    def run(
        self,
        user_input: str,
        thread_id: str = "default",
    ) -> str:
        """
        사용자 요청으로 Graph를 실행하고
        최종 자연어 답변을 반환합니다.
        """

        if (
            not isinstance(
                user_input,
                str,
            )
            or not user_input.strip()
        ):
            raise ValueError(
                "user_input은 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        if (
            not isinstance(
                thread_id,
                str,
            )
            or not thread_id.strip()
        ):
            raise ValueError(
                "thread_id는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        config = {
            "configurable": {
                "thread_id": thread_id.strip()
            }
        }

        normalized_user_input = self._normalize_bom_query(user_input)

        initial_state: BomAgentState = {
            "messages": [
                HumanMessage(
                    content=normalized_user_input
                )
            ],
            "user_query": normalized_user_input,
            "tool_steps": 0,
            "error": None,
        }

        existing_state = self.graph.get_state(
            config
        )

        if not existing_state.values.get(
            "design_change"
        ):
            initial_state["design_change"] = (
                create_initial_design_change_state()
            )

        with self.observability.observe(
            "display-bom-agent-request",
            as_type="agent",
            input_summary=summarize_text(normalized_user_input),
            metadata={"thread_id_present": bool(thread_id.strip())},
        ) as trace:
            final_state = self.graph.invoke(
                initial_state,
                config=config,
            )
            answer = self._extract_final_answer(final_state)
            trace.finish(output=summarize_text(answer))
            return answer

    def run_with_artifacts(self, user_input: str, thread_id: str = "default") -> dict:
        """한 Agent 턴의 답변과 MCP 다운로드 파일을 분리해 반환합니다."""
        config = {"configurable": {"thread_id": thread_id.strip()}}
        answer = self.run(user_input, thread_id=thread_id)
        after = self.graph.get_state(config)
        new_messages = self._current_turn_messages(
            after.values.get("messages", []), self._normalize_bom_query(user_input)
        )
        artifacts = self._extract_download_artifacts(new_messages)
        bom_views = self._extract_bom_views(new_messages)
        return {"answer": answer, "artifacts": artifacts, "bom_views": bom_views}

    @staticmethod
    def _extract_final_answer(final_state: BomAgentState) -> str:
        messages = final_state.get("messages", [])
        if not messages:
            raise RuntimeError("Graph execution returned no messages.")
        final_message = messages[-1]
        if not isinstance(final_message, AIMessage):
            raise RuntimeError("The final Graph message is not an AIMessage.")
        if not final_message.content:
            raise RuntimeError("The Agent did not produce a final answer.")
        return str(final_message.content)

    @staticmethod
    def _normalize_bom_query(user_input: str) -> str:
        """명확한 BOM 조회 표현을 하나의 표준 질의로 정규화합니다.

        화면 제목을 복사한 문장처럼 동사가 없는 표현도 `BOM 조회 대상 코드`가
        있으면 조회 요청으로 처리합니다. 코드가 하나일 때만 정규화하여
        설계변경 비교나 여러 코드가 포함된 일반 질문을 잘못 바꾸지 않습니다.
        """
        compact = " ".join(str(user_input).strip().split())
        upper = compact.upper()
        if "BOM" not in upper:
            return compact

        has_query_intent = any(
            marker in upper
            for marker in (
                "조회", "보여", "알려", "확인", "조회 대상 코드",
                "제품 BOM", "ASSY BOM", "ASSEMBLY BOM",
            )
        )
        if not has_query_intent:
            return compact

        codes = re.findall(r"(?<![A-Z0-9])[A-Z0-9]+(?:-[A-Z0-9]+)+(?![A-Z0-9])", upper)
        unique_codes = list(dict.fromkeys(codes))
        if len(unique_codes) != 1:
            return compact

        return f"{unique_codes[0]}의 BOM을 보여줘"

    @staticmethod
    def _current_turn_messages(messages: list, user_input: str) -> list:
        """마지막 사용자 요청부터 현재 응답까지의 메시지만 안정적으로 추출합니다.

        Checkpoint의 message merge/replace로 전체 개수가 달라져도 이전 턴의
        길이를 기준으로 자르지 않으므로 현재 get_bom ToolMessage를 놓치지 않습니다.
        """
        normalized = user_input.strip()
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if isinstance(message, HumanMessage) and str(message.content).strip() == normalized:
                return messages[index:]
        raise RuntimeError("현재 사용자 요청의 Agent 메시지 범위를 찾을 수 없습니다.")

    @staticmethod
    def _extract_bom_views(messages: list) -> list[list[dict]]:
        """get_bom Tool 결과를 공통 Streamlit BOM 렌더러용 데이터로 분리합니다."""
        views = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "get_bom":
                continue
            try:
                data = json.loads(str(message.content))
                if isinstance(data, list) and data:
                    views.append(data)
            except (TypeError, json.JSONDecodeError):
                continue
        return views

    @staticmethod
    def _extract_download_artifacts(messages: list) -> list[dict]:
        """MCP 다운로드 ToolMessage를 Streamlit용 파일 객체로 변환합니다."""
        artifacts = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name not in {
                "export_bom_excel", "export_design_change_report",
            }:
                continue
            try:
                data = json.loads(str(message.content))
                encoded = data.get("file_data_base64")
                if data.get("success") and encoded:
                    artifacts.append({
                        "file_name": data["file_name"],
                        "mime_type": data["mime_type"],
                        "file_bytes": base64.b64decode(encoded, validate=True),
                        "tool_name": message.name,
                    })
            except (ValueError, TypeError, json.JSONDecodeError, KeyError):
                continue
        return artifacts

    def get_design_change_state(
        self,
        thread_id: str = "default",
    ):
        """대화 Thread에 저장된 설계변경 Workflow 상태를 반환합니다."""

        if (
            not isinstance(thread_id, str)
            or not thread_id.strip()
        ):
            raise ValueError(
                "thread_id는 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        snapshot = self.graph.get_state(
            {
                "configurable": {
                    "thread_id": thread_id.strip()
                }
            }
        )

        return snapshot.values.get(
            "design_change",
            create_initial_design_change_state(),
        )
