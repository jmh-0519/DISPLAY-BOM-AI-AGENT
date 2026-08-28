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

from agents.analysis_macro_dispatch import MACRO_ANALYZE
from agents.bom_analysis_finalizer_node import (
    ANALYSIS_FINALIZE,
    BomAnalysisFinalizerNode,
    is_macro_analysis_tool_result,
)
from agents.bom_agent_node import BomAgentNode
from agents.bom_agent_router import (
    MCP_TOOLS,
    route_agent_response,
    route_mcp_tool_result,
)
from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_BOM_READ,
    FAST_CHAT,
    FAST_CURRENT_BOM_QUANTITY,
    FAST_WHERE_USED,
    BomGraphGateway,
)
from agents.bom_fast_path_nodes import (
    FAST_READ_FINALIZE,
    BomFastPathNodes,
    is_current_bom_quantity_tool_message,
    is_graph_fast_tool_result,
)
from agents.bom_agent_state import BomAgentState
from agents.design_change_workflow_state import (
    create_initial_design_change_state,
)
from agents.bom_mcp_tool_node import (
    BomMcpToolNode,
)
from agents.bom_macro_dispatch_node import BomMacroDispatchNode
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
from core.performance_profiler import performance_span, record_performance_event

from langgraph.checkpoint.memory import InMemorySaver

AGENT = "agent"


class BomAgentGraph:
    """
    Display BOM AI Agent의 LangGraph 실행 흐름입니다.

    START
      → Gateway Router
        → Fast Chat → END
        → Fast BOM/Where-used → MCP Tool Node → Fast Finalize → END
        → Deterministic Analysis Macro → MCP Tool Node → Analysis Finalizer → END
        → Agent Node → MCP Tool Node → Agent Node → END
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

        # Warm the MCP Tool schema once while Streamlit/Agent is being created.
        # Subsequent Agent turns use the process cache instead of starting a new
        # MCP stdio server just to list the same Tool definitions.
        mcp_client.get_tool_definitions()

        self.agent_node = BomAgentNode(
            client=client,
            mcp_client=mcp_client,
            skill_context=skill_context,
        )

        self.mcp_tool_node = BomMcpToolNode(
            mcp_client=mcp_client,
            observability=self.observability,
        )

        self.gateway = BomGraphGateway(
            phase3_active_steps=self.agent_node.PHASE3_ACTIVE_STEPS,
        )
        self.fast_path_nodes = BomFastPathNodes()
        self.macro_dispatch_node = BomMacroDispatchNode(
            self.gateway.analysis_macro_dispatch
        )
        self.analysis_finalizer_node = BomAnalysisFinalizerNode(
            client=client,
            deterministic=True,
        )

        self.checkpointer = (
            checkpointer
            if checkpointer is not None
            else InMemorySaver()
        )

        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the hybrid LangGraph with a workflow-aware entry gateway."""

        workflow = StateGraph(BomAgentState)

        workflow.add_node(
            FAST_CHAT,
            self._observed_node(FAST_CHAT, self.fast_path_nodes.chat),
        )
        workflow.add_node(
            FAST_BOM_READ,
            self._observed_node(FAST_BOM_READ, self.fast_path_nodes.bom_read),
        )
        workflow.add_node(
            FAST_WHERE_USED,
            self._observed_node(FAST_WHERE_USED, self.fast_path_nodes.where_used),
        )
        workflow.add_node(
            FAST_CURRENT_BOM_QUANTITY,
            self._observed_node(
                FAST_CURRENT_BOM_QUANTITY,
                self.fast_path_nodes.current_bom_quantity,
            ),
        )
        workflow.add_node(
            FAST_READ_FINALIZE,
            self._observed_node(
                FAST_READ_FINALIZE,
                self.fast_path_nodes.finalize_read,
            ),
        )
        workflow.add_node(
            MACRO_ANALYZE,
            self._observed_node(MACRO_ANALYZE, self.macro_dispatch_node),
        )
        workflow.add_node(
            ANALYSIS_FINALIZE,
            self._observed_node(
                ANALYSIS_FINALIZE,
                self.analysis_finalizer_node,
            ),
        )
        workflow.add_node(
            AGENT,
            self._observed_node(AGENT, self.agent_node),
        )
        workflow.add_node(
            MCP_TOOLS,
            self._observed_node(MCP_TOOLS, self.mcp_tool_node),
        )

        # True Graph-level Fast Path: high-confidence simple requests bypass
        # BomAgentNode entirely. Incomplete/complex/workflow-sensitive turns
        # enter the existing Agent path unchanged.
        workflow.add_conditional_edges(
            START,
            self._route_user_request,
            {
                FAST_CHAT: FAST_CHAT,
                FAST_BOM_READ: FAST_BOM_READ,
                FAST_WHERE_USED: FAST_WHERE_USED,
                FAST_CURRENT_BOM_QUANTITY: FAST_CURRENT_BOM_QUANTITY,
                MACRO_ANALYZE: MACRO_ANALYZE,
                AGENT_PATH: AGENT,
            },
        )

        workflow.add_edge(FAST_CHAT, END)
        workflow.add_edge(FAST_BOM_READ, MCP_TOOLS)
        workflow.add_edge(FAST_WHERE_USED, MCP_TOOLS)
        workflow.add_edge(FAST_CURRENT_BOM_QUANTITY, MCP_TOOLS)
        workflow.add_edge(MACRO_ANALYZE, MCP_TOOLS)
        workflow.add_edge(FAST_READ_FINALIZE, END)
        workflow.add_edge(ANALYSIS_FINALIZE, END)

        workflow.add_conditional_edges(
            AGENT,
            route_agent_response,
            {
                MCP_TOOLS: MCP_TOOLS,
                END: END,
            },
        )

        workflow.add_conditional_edges(
            MCP_TOOLS,
            self._route_mcp_tool_result,
            {
                AGENT: AGENT,
                ANALYSIS_FINALIZE: ANALYSIS_FINALIZE,
                FAST_READ_FINALIZE: FAST_READ_FINALIZE,
                END: END,
            },
        )

        return workflow.compile(checkpointer=self.checkpointer)

    def _route_user_request(self, state: BomAgentState) -> str:
        """Route the current turn at Graph entry before BomAgentNode executes."""
        with self.observability.observe(
            "langgraph.gateway",
            input_summary={
                "message_count": len(state.get("messages", [])),
                "workflow_step": (
                    (state.get("design_change") or {}).get("current_step")
                    or "NOT_STARTED"
                ),
            },
            metadata={"node": "gateway"},
        ) as span:
            route = self.gateway.route(state)
            record_performance_event(
                category="routing",
                name="graph.gateway.route",
                metadata={"route": route},
            )
            span.finish(output={"route": route})
            return route

    @staticmethod
    def _route_mcp_tool_result(state: BomAgentState) -> str:
        """Return Fast Tool results to an LLM-free finalizer when applicable."""
        normal_route = route_mcp_tool_result(state)
        if normal_route == END:
            return END
        if is_graph_fast_tool_result(state):
            return FAST_READ_FINALIZE
        if is_macro_analysis_tool_result(state):
            return ANALYSIS_FINALIZE
        return AGENT

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
                with performance_span(
                    "graph_node",
                    f"langgraph.{name}",
                    metadata={
                        "message_count": len(messages),
                        "tool_steps": state.get("tool_steps", 0),
                    },
                ):
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
            with performance_span(
                "request",
                "agent.request",
                metadata={"thread_id_present": bool(thread_id.strip())},
            ):
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
        where_used_views = self._extract_where_used_views(new_messages)
        cost_scan_views = self._extract_product_cost_scan_views(new_messages)
        plant_options = self._extract_plant_options(new_messages)
        tool_names = self._extract_tool_names(new_messages)
        candidate_panel_tools = {
            "analyze_design_change_candidates",
            "revalidate_design_change_analysis",
            "evaluate_replacement_candidates",
            "submit_candidate_additional_data",
        }
        terminal_error = bool(str(after.values.get("error") or "").strip())
        # STEP40-N2: a failed candidate-analysis Tool still leaves a ToolMessage
        # with the original Tool name.  Tool-name presence alone must therefore
        # never be used to hide the terminal error answer or render an empty
        # Phase3 panel.  Successful structured outputs may suppress duplicate LLM
        # prose; terminal errors must always remain visible to the user.
        render_phase3_panel = (
            bool(tool_names & candidate_panel_tools) and not terminal_error
        )
        suppress_answer = (
            bool(bom_views)
            or bool(where_used_views)
            or render_phase3_panel
            or bool(plant_options)
        ) and not terminal_error
        return {
            "answer": answer,
            "artifacts": artifacts,
            "bom_views": bom_views,
            "where_used_views": where_used_views,
            "cost_scan_views": cost_scan_views,
            "plant_options": plant_options,
            "workflow": self.get_design_change_state(thread_id),
            "active_bom_context": self.get_active_bom_context(thread_id),
            "render_phase3_panel": render_phase3_panel,
            "suppress_answer": suppress_answer,
            "tool_names": sorted(tool_names),
        }

    @staticmethod
    def _user_facing_tool_error(error_text: str) -> str:
        """Remove Tool/function names and machine error codes from UI text.

        The raw terminal error remains in Graph state/observability for debugging.
        Only the business-readable result is returned to Streamlit.
        """
        message = str(error_text or "").strip()
        if not message:
            return "요청을 처리할 수 없습니다."

        lower_message = message.lower()
        if "old_item_code must reference an active item" in lower_message:
            return (
                "요청한 자재를 활성 자재 기준정보에서 찾을 수 없습니다. "
                "자재 코드를 확인해 주세요."
            )
        if "new_item_code must reference an active item" in lower_message:
            return (
                "변경 후보 자재를 활성 자재 기준정보에서 찾을 수 없습니다. "
                "자재 코드를 확인해 주세요."
            )

        message = re.sub(
            r"^\s*[A-Za-z0-9_.-]+\s*:\s*Error executing tool\s+"
            r"[A-Za-z0-9_.-]+\s*:\s*",
            "",
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(
            r"^\s*Error executing tool\s+[A-Za-z0-9_.-]+\s*:\s*",
            "",
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(
            r"^\s*[A-Za-z0-9_.-]+\s*:\s*",
            "",
            message,
            count=1,
        )
        message = re.sub(r"^\s*[A-Z][A-Z0-9_]{3,}\s*:\s*", "", message)
        return message.strip() or "요청을 처리할 수 없습니다."

    @staticmethod
    def _extract_final_answer(final_state: BomAgentState) -> str:
        terminal_error = str(final_state.get("error") or "").strip()
        if terminal_error:
            return BomAgentGraph._user_facing_tool_error(terminal_error)

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

        # BOM 조회가 최종 목적이 아니라 다른 업무를 위한 근거 조회인 복합 요청은
        # 절대 단순 BOM 조회 문장으로 축약하지 않는다. 예를 들어
        # "BOM 정보를 확인해서 원가를 낮출 대체 자재를 찾아줘"를
        # "BOM을 보여줘"로 바꾸면 COST/대체/제외 조건이 모두 사라진다.
        # Query normalization은 UI 제목 복사나 순수 BOM 조회 표현에만 적용한다.
        normalized_lower = compact.lower()
        business_intent_markers = (
            "원가", "비용", "절감", "저렴", "cost",
            "대체", "변경", "교체", "후보", "단종", "eol",
            "재고", "납기", "품질", "불량", "공급",
            "추가", "삭제", "제거", "없애", "빼", "제외", "수량", "적용", "승인",
            "비교", "영향", "추천",
            "역방향", "where used", "where-used", "사용처", "상위 assy", "상위 모델",
            "사용된 모델", "포함하는 모델", "가지고 있는 모델",
        )
        if any(marker in normalized_lower for marker in business_intent_markers):
            return compact

        codes = re.findall(r"(?<![A-Z0-9])[A-Z0-9]+(?:-[A-Z0-9]+)+(?![A-Z0-9])", upper)
        unique_codes = list(dict.fromkeys(codes))
        if len(unique_codes) != 1:
            return compact

        # 대화형 PLANT Gate 도입 후에는 사용자가 명시한 PLANT를 Query Normalization에서
        # 잃어버리면 안 된다. BOM 표현만 표준화하고 PLANT Context는 보존한다.
        plant_match = re.search(r"(?<![A-Z0-9])P\d{2,}(?![A-Z0-9])", upper)
        if plant_match:
            return f"{plant_match.group(0)}에서 {unique_codes[0]}의 BOM을 보여줘"
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
    def _extract_tool_names(messages: list) -> set[str]:
        return {
            str(message.name)
            for message in messages
            if isinstance(message, ToolMessage) and message.name
        }

    @staticmethod
    def _extract_bom_views(messages: list) -> list[list[dict]]:
        """get_bom Tool 결과를 공통 Streamlit BOM 렌더러용 데이터로 분리합니다."""
        views = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "get_bom":
                continue
            if is_current_bom_quantity_tool_message(message):
                # Contextual fact queries reuse get_bom evidence internally but
                # must answer only the requested value, not redraw the full BOM.
                continue
            try:
                data = json.loads(str(message.content))
                if isinstance(data, list) and data:
                    views.append(data)
            except (TypeError, json.JSONDecodeError):
                continue
        return views

    @staticmethod
    def _extract_where_used_views(messages: list) -> list[dict]:
        """Extract reverse BOM payloads for structured Streamlit rendering."""
        views: list[dict] = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "get_bom_where_used":
                continue
            try:
                data = json.loads(str(message.content))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                views.append(data)
        return views

    @staticmethod
    def _extract_plant_options(messages: list) -> list[dict]:
        """Extract a list_plants Observation for Streamlit button rendering."""
        options: list[dict] = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "list_plants":
                continue
            try:
                data = json.loads(str(message.content))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, list):
                options = [row for row in data if isinstance(row, dict) and row.get("plant_code")]
        return options

    @staticmethod
    def _extract_product_cost_scan_views(messages: list) -> list[dict]:
        """Extract read-only product-wide cost scan payloads for Streamlit."""
        views: list[dict] = []
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != "scan_product_cost_reduction_candidates":
                continue
            try:
                data = json.loads(str(message.content))
                if isinstance(data, dict) and data.get("scan_type") == "PRODUCT_COST_REDUCTION":
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

    def get_active_bom_context(
        self,
        thread_id: str = "default",
    ) -> dict | None:
        """Return the latest single-product BOM context for this chat thread."""
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id는 비어 있지 않은 문자열이어야 합니다.")

        snapshot = self.graph.get_state(
            {
                "configurable": {
                    "thread_id": thread_id.strip(),
                }
            }
        )
        context = snapshot.values.get("active_bom_context")
        return dict(context) if isinstance(context, dict) else None

    def can_inherit_active_bom_context(
        self,
        user_input: str,
        thread_id: str = "default",
    ) -> bool:
        """Use the same Gateway policy before Streamlit's PLANT pre-gate."""
        return self.gateway.can_inherit_active_bom_context(
            user_input,
            self.get_active_bom_context(thread_id),
        )

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

    def update_design_change_state(
        self,
        workflow_state: dict,
        thread_id: str = "default",
    ) -> None:
        """Streamlit 직접 MCP Action 결과를 LangGraph Checkpoint와 동기화합니다."""

        if not isinstance(workflow_state, dict):
            raise TypeError("workflow_state는 dictionary여야 합니다.")
        if not thread_id or not str(thread_id).strip():
            raise ValueError("thread_id는 비어 있지 않은 문자열이어야 합니다.")

        self.graph.update_state(
            {
                "configurable": {
                    "thread_id": str(thread_id).strip(),
                }
            },
            {"design_change": dict(workflow_state)},
        )
