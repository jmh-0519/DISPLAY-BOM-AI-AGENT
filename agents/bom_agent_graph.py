from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
import base64
import json
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
    ) -> None:
        self.agent_node = BomAgentNode(
            client=client,
            mcp_client=mcp_client,
            skill_context=skill_context,
        )

        self.mcp_tool_node = BomMcpToolNode(
            mcp_client=mcp_client,
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
            self.agent_node,
        )
        workflow.add_node(
            MCP_TOOLS,
            self.mcp_tool_node,
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

        initial_state: BomAgentState = {
            "messages": [
                HumanMessage(
                    content=user_input.strip()
                )
            ],
            "user_query": user_input.strip(),
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

        final_state = self.graph.invoke(
            initial_state,
            config=config,
        )

        messages = final_state.get(
            "messages",
            [],
        )

        if not messages:
            raise RuntimeError(
                "Graph 실행 결과에 "
                "메시지가 없습니다."
            )

        final_message = messages[-1]

        if not isinstance(
            final_message,
            AIMessage,
        ):
            raise RuntimeError(
                "Graph의 마지막 메시지가 "
                "AIMessage가 아닙니다."
            )

        if not final_message.content:
            raise RuntimeError(
                "Agent가 최종 답변을 "
                "생성하지 않았습니다."
            )

        return str(final_message.content)

    def run_with_artifacts(self, user_input: str, thread_id: str = "default") -> dict:
        """한 Agent 턴의 답변과 MCP 다운로드 파일을 분리해 반환합니다."""
        config = {"configurable": {"thread_id": thread_id.strip()}}
        before = self.graph.get_state(config)
        before_count = len(before.values.get("messages", []))
        answer = self.run(user_input, thread_id=thread_id)
        after = self.graph.get_state(config)
        new_messages = after.values.get("messages", [])[before_count:]
        artifacts = self._extract_download_artifacts(new_messages)
        return {"answer": answer, "artifacts": artifacts}

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
