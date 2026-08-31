import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)

from agents.bom_agent_state import BomAgentState
from agents.design_change_workflow_state import (
    DesignChangeWorkflowState,
    apply_design_change_tool_result,
    create_initial_design_change_state,
)
from mcp_client.client import DisplayBomMcpClient
from core.performance_profiler import performance_span
from core.observability import (
    LangfuseObservability,
    get_observability,
    summarize_value,
)


class BomMcpToolNode:
    """
    AIMessage의 Tool Call을 읽고
    MCP Tool을 실행하는 LangGraph Node입니다.
    """

    def __init__(
        self,
        mcp_client: DisplayBomMcpClient,
        observability: LangfuseObservability | None = None,
    ) -> None:
        self.mcp_client = mcp_client
        self.observability = observability or get_observability()

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
                "MCP Tool Node 실행에는 "
                "하나 이상의 메시지가 필요합니다."
            )

        last_message = messages[-1]

        if not isinstance(
            last_message,
            AIMessage,
        ):
            raise TypeError(
                "MCP Tool Node의 마지막 메시지는 "
                "AIMessage여야 합니다."
            )

        if not last_message.tool_calls:
            raise ValueError(
                "실행할 Tool Call이 없습니다."
            )

        tool_messages: list[ToolMessage] = []
        design_change_update = state.get(
            "design_change"
        )
        active_bom_context_update = state.get("active_bom_context")
        terminal_error: str | None = None

        for tool_index, tool_call in enumerate(last_message.tool_calls):
            tool_name = tool_call["name"]
            arguments = tool_call["args"]
            tool_call_id = tool_call["id"]

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    "Tool arguments는 "
                    "dictionary여야 합니다."
                )

            if tool_name in {
                "scan_product_cost_reduction_candidates",
                "analyze_design_change_candidates", "revalidate_design_change_analysis",
                "preview_design_change_analysis_impact", "create_design_change_request_from_analysis",
                "explain_design_change_analysis_session", "explain_design_change_analysis_candidate",
                "compare_design_change_analysis_candidates",
                "create_design_change_request", "evaluate_replacement_candidates",
                "submit_candidate_additional_data", "select_candidate_and_supplier",
                "approve_candidate_impact", "record_exception_approval",
                "create_design_change_preview", "record_final_apply_approval",
                "apply_approved_change_request", "get_change_request_result",
                "get_design_change_analysis", "get_candidate_evaluation_detail",
                "compare_design_change_candidates",
            }:
                try:
                    self._validate_design_change_request(
                        tool_name,
                        design_change_update,
                        arguments,
                    )
                except ValueError as error:
                    recovery = self._design_change_transition_error(
                        tool_name,
                        design_change_update,
                        str(error),
                    )
                    tool_messages.append(
                        ToolMessage(
                            content=self._serialize_tool_result(recovery),
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        )
                    )
                    continue

            if tool_name in {"get_bom", "get_bom_where_used"}:
                # A new read context replaces the previous active product BOM.
                # WHERE_USED has no single product root, so it clears the scope.
                active_bom_context_update = None

            try:
                with self.observability.observe(
                    "mcp.tool",
                    as_type="tool",
                    input_summary={
                        "tool_name": tool_name,
                        "arguments": summarize_value(arguments),
                    },
                    metadata={"tool_name": tool_name},
                ) as span:
                    with performance_span(
                        "mcp_tool",
                        tool_name,
                        metadata={"argument_count": len(arguments)},
                    ):
                        tool_result = self.mcp_client.call_tool(
                            tool_name=tool_name,
                            arguments=arguments,
                        )
                    span.finish(output=summarize_value(tool_result))
            except Exception as error:
                error_text = str(error).strip() or type(error).__name__
                recovery = {
                    "success": False,
                    "error_code": "TOOL_EXECUTION_FAILED",
                    "tool_name": tool_name,
                    "message": error_text,
                    "production_bom_modified": False,
                }
                tool_messages.append(
                    ToolMessage(
                        content=self._serialize_tool_result(recovery),
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                )

                # A deterministic MCP/business error must not be fed back to the
                # LLM for the same Tool to be retried until MAX_TOOL_STEPS. End
                # this Graph run after the first failure and surface the original
                # error to the user. Complete any remaining Tool Call IDs as
                # skipped so the persisted conversation remains protocol-valid.
                terminal_error = f"{tool_name}: {error_text}"
                for remaining_call in last_message.tool_calls[tool_index + 1:]:
                    skipped_name = remaining_call["name"]
                    skipped = {
                        "success": False,
                        "error_code": "SKIPPED_AFTER_TOOL_ERROR",
                        "tool_name": skipped_name,
                        "message": (
                            "앞선 Tool 실행 오류로 같은 Agent 턴의 후속 Tool 실행을 중단했습니다."
                        ),
                        "production_bom_modified": False,
                    }
                    tool_messages.append(
                        ToolMessage(
                            content=self._serialize_tool_result(skipped),
                            tool_call_id=remaining_call["id"],
                            name=skipped_name,
                        )
                    )
                break

            if tool_name == "get_bom" and tool_result:
                product_id = str(arguments.get("product_id") or "").strip().upper()
                plant_code = str(arguments.get("plant_code") or "").strip().upper()
                if product_id and plant_code:
                    active_bom_context_update = {
                        "product_id": product_id,
                        "plant_code": plant_code,
                        "source": "get_bom",
                    }

            if tool_name in {
                "scan_product_cost_reduction_candidates",
                "analyze_design_change_candidates", "revalidate_design_change_analysis",
                "preview_design_change_analysis_impact", "create_design_change_request_from_analysis",
                "explain_design_change_analysis_session", "explain_design_change_analysis_candidate",
                "compare_design_change_analysis_candidates",
                "create_design_change_request", "evaluate_replacement_candidates",
                "submit_candidate_additional_data", "select_candidate_and_supplier",
                "approve_candidate_impact", "record_exception_approval",
                "create_design_change_preview", "record_final_apply_approval",
                "apply_approved_change_request", "get_change_request_result",
                "get_design_change_analysis", "get_candidate_evaluation_detail",
                "compare_design_change_candidates",
            }:
                design_change_update = self._build_design_change_workflow_state(
                    tool_name, design_change_update, tool_result
                )

            serialized_result = (
                self._serialize_tool_result(
                    tool_result
                )
            )

            tool_messages.append(
                ToolMessage(
                    content=serialized_result,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                )
            )

        current_tool_steps = state.get(
            "tool_steps",
            0,
        )

        result: BomAgentState = {
            "messages": tool_messages,
            "tool_steps": (
                current_tool_steps + 1
            ),
            "error": terminal_error,
        }

        if design_change_update is not None:
            result["design_change"] = (
                design_change_update
            )

        result["active_bom_context"] = active_bom_context_update

        return result

    @staticmethod
    def _build_design_change_workflow_state(tool_name, workflow_state, tool_result):
        return apply_design_change_tool_result(
            tool_name,
            workflow_state,
            tool_result,
        )

    @staticmethod
    def _validate_design_change_request(tool_name, workflow_state, arguments):
        state = workflow_state or create_initial_design_change_state()
        step = state.get("current_step", "NOT_STARTED")
        allowed = {
            "scan_product_cost_reduction_candidates": {
                "NOT_STARTED", "ANALYSIS_READY", "ANALYSIS_REVALIDATED",
                "ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED", "REQUESTED",
                "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
                "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED",
                "CANDIDATE_APPROVED", "WAITING_FINAL_APPROVAL", "FINAL_APPROVED",
                "APPLIED", "REPORT_COMPLETED", "BLOCKED",
            },
            "analyze_design_change_candidates": {
                "NOT_STARTED", "ANALYSIS_READY", "ANALYSIS_REVALIDATED",
                "ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED", "APPLIED", "BLOCKED",
            },
            "revalidate_design_change_analysis": {"ANALYSIS_READY", "ANALYSIS_REVALIDATED"},
            "preview_design_change_analysis_impact": {"ANALYSIS_READY", "ANALYSIS_REVALIDATED", "ANALYSIS_CONFIRMED", "ANALYSIS_IMPACT_REVIEW"},
            "create_design_change_request_from_analysis": {"ANALYSIS_CONFIRMED"},
            "explain_design_change_analysis_session": {"ANALYSIS_READY", "ANALYSIS_REVALIDATED", "ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED"},
            "explain_design_change_analysis_candidate": {"ANALYSIS_READY", "ANALYSIS_REVALIDATED", "ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED"},
            "compare_design_change_analysis_candidates": {"ANALYSIS_READY", "ANALYSIS_REVALIDATED", "ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED"},
            "create_design_change_request": {"NOT_STARTED", "APPLIED", "BLOCKED"},
            "evaluate_replacement_candidates": {
                "REQUESTED", "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
            },
            "submit_candidate_additional_data": {"WAITING_CANDIDATE_APPROVAL", "CONDITIONAL_REVIEW_REQUIRED"},
            "select_candidate_and_supplier": {"WAITING_CANDIDATE_APPROVAL", "IMPACT_REVIEW_REQUIRED"},
            "approve_candidate_impact": {"IMPACT_REVIEW_REQUIRED"},
            "record_exception_approval": {"CONDITIONAL_REVIEW_REQUIRED", "CANDIDATE_APPROVED"},
            "create_design_change_preview": {"CANDIDATE_APPROVED"},
            "record_final_apply_approval": {"WAITING_FINAL_APPROVAL"},
            "apply_approved_change_request": {"FINAL_APPROVED"},
            "get_change_request_result": {
                "REQUESTED", "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
                "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED", "WAITING_FINAL_APPROVAL", "FINAL_APPROVED",
                "APPLIED", "BLOCKED",
            },
            "get_design_change_analysis": {
                "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
                "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED", "WAITING_FINAL_APPROVAL",
                "FINAL_APPROVED", "APPLIED", "BLOCKED",
            },
            "get_candidate_evaluation_detail": {
                "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
                "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED", "WAITING_FINAL_APPROVAL",
                "FINAL_APPROVED", "APPLIED", "BLOCKED",
            },
            "compare_design_change_candidates": {
                "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
                "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED", "WAITING_FINAL_APPROVAL",
                "FINAL_APPROVED", "APPLIED", "BLOCKED",
            },
        }
        if step not in allowed[tool_name]:
            raise ValueError(f"{tool_name} cannot run from Design Change step {step}")
        analysis_tools = {
            "scan_product_cost_reduction_candidates",
            "analyze_design_change_candidates", "revalidate_design_change_analysis",
            "preview_design_change_analysis_impact", "create_design_change_request_from_analysis",
            "explain_design_change_analysis_session", "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        }
        if tool_name not in analysis_tools:
            expected_request = state.get("request_id")
            supplied_request = arguments.get("request_id")
            if expected_request and supplied_request and supplied_request != expected_request:
                raise ValueError("Design Change tool request_id does not match the active workflow")

    @staticmethod
    def _design_change_transition_error(tool_name, workflow_state, message):
        state = workflow_state or create_initial_design_change_state()
        step = state.get("current_step", "NOT_STARTED")
        allowed_next = {
            "NOT_STARTED": ["analyze_design_change_candidates"],
            "ANALYSIS_READY": ["analyze_design_change_candidates", "revalidate_design_change_analysis", "explain_design_change_analysis_session", "explain_design_change_analysis_candidate", "compare_design_change_analysis_candidates"],
            "ANALYSIS_REVALIDATED": ["analyze_design_change_candidates", "revalidate_design_change_analysis", "explain_design_change_analysis_session", "explain_design_change_analysis_candidate", "compare_design_change_analysis_candidates"],
            "ANALYSIS_IMPACT_REVIEW": ["analyze_design_change_candidates", "explain_design_change_analysis_session", "explain_design_change_analysis_candidate", "compare_design_change_analysis_candidates"],
            "ANALYSIS_CONFIRMED": ["analyze_design_change_candidates", "create_design_change_request_from_analysis", "explain_design_change_analysis_session", "explain_design_change_analysis_candidate", "compare_design_change_analysis_candidates"],
            "REQUESTED": ["evaluate_replacement_candidates"],
            "CANDIDATES_EVALUATED": ["evaluate_replacement_candidates"],
            "WAITING_CANDIDATE_APPROVAL": [
                "evaluate_replacement_candidates",
                "submit_candidate_additional_data",
                "select_candidate_and_supplier",
                "get_design_change_analysis",
                "get_candidate_evaluation_detail",
                "compare_design_change_candidates",
            ],
            "CONDITIONAL_REVIEW_REQUIRED": [
                "submit_candidate_additional_data",
                "record_exception_approval",
                "get_design_change_analysis",
                "get_candidate_evaluation_detail",
                "compare_design_change_candidates",
            ],
            "IMPACT_REVIEW_REQUIRED": [
                "select_candidate_and_supplier",
                "approve_candidate_impact",
                "get_design_change_analysis",
                "get_candidate_evaluation_detail",
                "compare_design_change_candidates",
            ],
            "CANDIDATE_APPROVED": [
                "record_exception_approval",
                "create_design_change_preview",
            ],
            "WAITING_FINAL_APPROVAL": ["record_final_apply_approval"],
            "FINAL_APPROVED": ["apply_approved_change_request"],
            "APPLIED": ["create_design_change_request"],
            "BLOCKED": ["create_design_change_request"],
        }.get(step, [])
        return {
            "success": False,
            "error_code": "INVALID_DESIGN_CHANGE_TRANSITION",
            "attempted_tool": tool_name,
            "current_step": step,
            "allowed_next_tools": allowed_next,
            "message": message,
            "production_bom_modified": False,
        }

    @staticmethod
    def _serialize_tool_result(
        data: Any,
    ) -> str:
        """
        MCP Tool 실행 결과를
        ToolMessage용 문자열로 변환합니다.
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
