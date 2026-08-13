import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)

from agents.bom_agent_state import BomAgentState
from agents.design_change_workflow_state import (
    DesignChangeWorkflowState,
    create_initial_design_change_state,
)
from mcp_client.client import DisplayBomMcpClient


class BomMcpToolNode:
    """
    AIMessage의 Tool Call을 읽고
    MCP Tool을 실행하는 LangGraph Node입니다.
    """

    def __init__(
        self,
        mcp_client: DisplayBomMcpClient,
    ) -> None:
        self.mcp_client = mcp_client

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

        for tool_call in last_message.tool_calls:
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

            if tool_name == "create_design_change_preview":
                self._validate_preview_request(
                    workflow_state=design_change_update,
                    arguments=arguments,
                )
            elif tool_name == "record_design_change_decision":
                self._validate_approval_request(
                    workflow_state=design_change_update,
                    arguments=arguments,
                )
            elif tool_name == "apply_approved_design_change":
                self._validate_apply_request(
                    workflow_state=design_change_update,
                    arguments=arguments,
                )
            elif tool_name == "evaluate_bom_review":
                self._validate_review_request(
                    workflow_state=design_change_update,
                    arguments=arguments,
                )
            elif tool_name in {
                "create_review_bom", "run_ai_bom_review",
                "generate_design_change_report", "apply_reviewed_bom",
            }:
                self._validate_ai_workflow_request(
                    tool_name, design_change_update, arguments
                )

            tool_result = (
                self.mcp_client.call_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                )
            )

            if tool_name == "analyze_design_change":
                design_change_update = (
                    self._build_analysis_state(
                        arguments=arguments,
                        tool_result=tool_result,
                    )
                )
            elif tool_name == "create_design_change_preview":
                design_change_update = self._build_preview_state(
                    workflow_state=design_change_update,
                    tool_result=tool_result,
                )
            elif tool_name == "record_design_change_decision":
                design_change_update = self._build_approval_state(
                    workflow_state=design_change_update,
                    tool_result=tool_result,
                )
            elif tool_name == "apply_approved_design_change":
                design_change_update = self._build_apply_state(
                    workflow_state=design_change_update,
                    tool_result=tool_result,
                )
            elif tool_name == "evaluate_bom_review":
                design_change_update = self._build_review_state(
                    workflow_state=design_change_update,
                    tool_result=tool_result,
                )
            elif tool_name in {
                "create_ai_change_request", "create_review_bom",
                "run_ai_bom_review", "generate_design_change_report",
                "apply_reviewed_bom",
            }:
                design_change_update = self._build_ai_workflow_state(
                    tool_name, design_change_update, arguments, tool_result
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
            "error": None,
        }

        if design_change_update is not None:
            result["design_change"] = (
                design_change_update
            )

        return result

    @staticmethod
    def _build_analysis_state(
        arguments: dict[str, Any],
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        """설계변경 분석 Tool 결과를 Workflow 상태로 변환합니다."""

        if not isinstance(tool_result, dict):
            raise RuntimeError(
                "analyze_design_change 결과가 "
                "예상한 객체 형식이 아닙니다."
            )

        analysis_status = str(
            tool_result.get("result", "")
        ).strip().upper()

        if analysis_status not in {
            "PASS",
            "CONDITIONAL",
            "FAIL",
        }:
            raise RuntimeError(
                "analyze_design_change 결과에 "
                "올바른 result가 없습니다."
            )

        workflow_state = (
            create_initial_design_change_state()
        )
        workflow_state.update(
            {
                "product_id": arguments.get(
                    "product_id"
                ),
                "old_material_id": arguments.get(
                    "old_material_id"
                ),
                "new_material_id": arguments.get(
                    "new_material_id"
                ),
                "as_of_date": arguments.get(
                    "as_of_date"
                ),
                "analysis_status": analysis_status,
                "analysis_result": tool_result,
                "current_step": (
                    "ANALYSIS_BLOCKED"
                    if analysis_status == "FAIL"
                    else "ANALYSIS_COMPLETED"
                ),
            }
        )

        return workflow_state

    @staticmethod
    def _validate_preview_request(
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
    ) -> None:
        """같은 분석 건이 완료된 경우에만 Preview 호출을 허용합니다."""

        if not workflow_state or workflow_state.get(
            "analysis_status"
        ) not in {"PASS", "CONDITIONAL"}:
            raise RuntimeError(
                "PASS 또는 CONDITIONAL 분석 완료 후 Preview를 생성할 수 있습니다."
            )

        for field_name in (
            "product_id",
            "old_material_id",
            "new_material_id",
        ):
            saved = str(
                workflow_state.get(field_name) or ""
            ).strip().upper()
            requested = str(
                arguments.get(field_name) or ""
            ).strip().upper()
            if saved != requested:
                raise RuntimeError(
                    "분석된 설계변경과 Preview 요청의 대상이 일치하지 않습니다."
                )

    @staticmethod
    def _build_preview_state(
        workflow_state: DesignChangeWorkflowState | None,
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        if not workflow_state:
            raise RuntimeError("설계변경 분석 상태가 없습니다.")
        if not isinstance(tool_result, dict) or not tool_result.get("success"):
            raise RuntimeError("Preview Tool 결과가 올바르지 않습니다.")

        revision = tool_result.get("preview_revision")
        if not isinstance(revision, str) or not revision.strip():
            raise RuntimeError("Preview Revision이 반환되지 않았습니다.")

        updated = dict(workflow_state)
        updated.update(
            {
                "preview_status": "COMPLETED",
                "preview_revision": revision,
                "preview_result": tool_result,
                "review_status": "WAITING",
                "current_step": "WAITING_REVIEW",
            }
        )
        return updated

    @staticmethod
    def _validate_approval_request(
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
    ) -> None:
        """품평 승인된 동일 Preview의 최종 적용 승인만 허용합니다."""

        if not workflow_state:
            raise RuntimeError("승인할 설계변경 Workflow 상태가 없습니다.")
        if workflow_state.get("review_status") != "APPROVED" or (
            workflow_state.get("approval_status") != "WAITING"
        ) or workflow_state.get("current_step") != "WAITING_FINAL_APPROVAL":
            raise RuntimeError("품평 승인 후 최종 적용 승인 대기 중인 Preview만 처리할 수 있습니다.")

        saved_revision = str(
            workflow_state.get("preview_revision") or ""
        ).strip()
        requested_revision = str(
            arguments.get("preview_revision") or ""
        ).strip()
        if not saved_revision or saved_revision != requested_revision:
            raise RuntimeError("승인 대상 Preview Revision이 일치하지 않습니다.")

        decision = str(arguments.get("decision") or "").strip().upper()
        if decision not in {"APPROVE", "REJECT"}:
            raise RuntimeError("승인 결정은 APPROVE 또는 REJECT여야 합니다.")

    @staticmethod
    def _build_approval_state(
        workflow_state: DesignChangeWorkflowState | None,
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        if not workflow_state:
            raise RuntimeError("설계변경 Workflow 상태가 없습니다.")
        if not isinstance(tool_result, dict) or not tool_result.get("success"):
            raise RuntimeError("승인·반려 Tool 결과가 올바르지 않습니다.")
        if tool_result.get("production_bom_modified") is not False:
            raise RuntimeError("승인 단계에서는 Production BOM을 변경할 수 없습니다.")

        decision = str(tool_result.get("decision") or "").strip().upper()
        if decision not in {"APPROVE", "REJECT"}:
            raise RuntimeError("승인·반려 Tool 결과에 올바른 decision이 없습니다.")
        if tool_result.get("preview_revision") != workflow_state.get(
            "preview_revision"
        ):
            raise RuntimeError("승인 결과의 Preview Revision이 일치하지 않습니다.")

        updated = dict(workflow_state)
        updated.update(
            {
                "approval_status": (
                    "APPROVED" if decision == "APPROVE" else "REJECTED"
                ),
                "approval_decision": decision,
                "approval_comment": tool_result.get("comment"),
                "approval_result": tool_result,
                "approved_preview_revision": tool_result["preview_revision"],
                "current_step": (
                    "READY_TO_APPLY"
                    if decision == "APPROVE"
                    else "CHANGE_REJECTED"
                ),
            }
        )
        return updated

    @staticmethod
    def _validate_apply_request(
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
    ) -> None:
        if not workflow_state or workflow_state.get("current_step") != "READY_TO_APPLY":
            raise RuntimeError("명시적으로 승인되어 READY_TO_APPLY인 변경만 적용할 수 있습니다.")
        if workflow_state.get("approval_status") != "APPROVED":
            raise RuntimeError("승인 완료된 설계변경만 적용할 수 있습니다.")
        if workflow_state.get("review_status") != "APPROVED":
            raise RuntimeError("품평회에서 승인된 설계변경만 적용할 수 있습니다.")
        if workflow_state.get("reviewed_preview_revision") != workflow_state.get(
            "approved_preview_revision"
        ):
            raise RuntimeError("품평 승인 Revision과 최종 승인 Revision이 일치하지 않습니다.")
        if workflow_state.get("apply_status") in {"COMPLETED", "FAILED"}:
            raise RuntimeError("이미 적용 처리된 설계변경은 다시 적용할 수 없습니다.")
        saved_revision = str(workflow_state.get("approved_preview_revision") or "").strip()
        if saved_revision != str(arguments.get("preview_revision") or "").strip():
            raise RuntimeError("승인된 Preview Revision과 적용 요청이 일치하지 않습니다.")
        for field in ("product_id", "old_material_id", "new_material_id"):
            if str(workflow_state.get(field) or "").strip().upper() != str(arguments.get(field) or "").strip().upper():
                raise RuntimeError("승인된 설계변경과 적용 요청의 대상이 일치하지 않습니다.")
        saved_date = str(workflow_state.get("as_of_date") or "").strip()
        requested_date = str(arguments.get("preview_as_of_date") or "").strip()
        if saved_date != requested_date:
            raise RuntimeError("승인된 Preview 기준일과 적용 요청이 일치하지 않습니다.")

    @staticmethod
    def _build_apply_state(
        workflow_state: DesignChangeWorkflowState | None,
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        if not workflow_state or not isinstance(tool_result, dict):
            raise RuntimeError("Controlled Apply 결과가 올바르지 않습니다.")
        if not tool_result.get("success") or tool_result.get("result") != "APPLIED":
            raise RuntimeError("Production BOM 적용에 실패했습니다.")
        if tool_result.get("production_bom_modified") is not True:
            raise RuntimeError("적용 결과에 Production BOM 변경 확인이 없습니다.")
        if tool_result.get("preview_revision") != workflow_state.get("approved_preview_revision"):
            raise RuntimeError("적용된 Preview Revision이 승인 Revision과 일치하지 않습니다.")
        updated = dict(workflow_state)
        updated.update({
            "apply_status": "COMPLETED",
            "apply_result": tool_result,
            "application_id": tool_result.get("application_id"),
            "current_step": "APPLY_COMPLETED",
        })
        return updated

    @staticmethod
    def _validate_review_request(
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
    ) -> None:
        if not workflow_state or workflow_state.get("current_step") != "WAITING_REVIEW":
            raise RuntimeError("Preview 생성 후 Production BOM 적용 전에만 품평회를 진행할 수 있습니다.")
        if workflow_state.get("preview_status") != "COMPLETED":
            raise RuntimeError("품평 대상 Preview가 완료 상태가 아닙니다.")
        if workflow_state.get("apply_status") == "COMPLETED":
            raise RuntimeError("이미 Production BOM에 적용된 변경은 사전 품평할 수 없습니다.")
        if workflow_state.get("review_status") in {"COMPLETED", "FAILED"}:
            raise RuntimeError("이미 품평 검증이 완료된 설계변경입니다.")
        if str(workflow_state.get("preview_revision") or "").strip() != str(
            arguments.get("preview_revision") or ""
        ).strip():
            raise RuntimeError("품평 대상 Preview Revision이 일치하지 않습니다.")
        for field in ("product_id", "old_material_id", "new_material_id"):
            if str(workflow_state.get(field) or "").strip().upper() != str(
                arguments.get(field) or ""
            ).strip().upper():
                raise RuntimeError("Preview 설계변경과 품평 요청의 대상이 일치하지 않습니다.")

    @staticmethod
    def _build_review_state(
        workflow_state: DesignChangeWorkflowState | None,
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        if not workflow_state or not isinstance(tool_result, dict):
            raise RuntimeError("BOM 품평 검증 결과가 올바르지 않습니다.")
        if not tool_result.get("success"):
            raise RuntimeError("BOM 품평 검증에 실패했습니다.")
        if tool_result.get("production_bom_modified") is not False:
            raise RuntimeError("품평 검증 Tool은 Production BOM을 변경할 수 없습니다.")
        if tool_result.get("preview_revision") != workflow_state.get("preview_revision"):
            raise RuntimeError("품평 결과의 Preview Revision이 일치하지 않습니다.")
        review_result = str(tool_result.get("review_result") or "").strip().upper()
        if review_result not in {"APPROVED", "CONDITIONAL", "REJECTED"}:
            raise RuntimeError("품평 결과에 올바른 review_result가 없습니다.")
        updated = dict(workflow_state)
        updated.update({
            "review_status": review_result,
            "review_result": tool_result,
            "reviewed_preview_revision": tool_result["preview_revision"],
            "approval_status": "WAITING" if review_result == "APPROVED" else "NOT_STARTED",
            "current_step": {
                "APPROVED": "WAITING_FINAL_APPROVAL",
                "CONDITIONAL": "REVIEW_CONDITIONAL",
                "REJECTED": "REVIEW_REJECTED",
            }[review_result],
        })
        return updated

    @staticmethod
    def _validate_ai_workflow_request(
        tool_name: str,
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
    ) -> None:
        if not workflow_state:
            raise RuntimeError("먼저 AI 설계변경 요청을 생성해야 합니다.")
        required_step = {
            "create_review_bom": "CHANGE_REQUESTED",
            "run_ai_bom_review": "REVIEW_BOM_CREATED",
            "generate_design_change_report": "AI_REVIEW_COMPLETED",
            "apply_reviewed_bom": "WAITING_FINAL_APPLY",
        }[tool_name]
        if workflow_state.get("current_step") != required_step:
            raise RuntimeError(f"{required_step} 상태에서만 {tool_name}을 실행할 수 있습니다.")
        if tool_name in {"create_review_bom", "generate_design_change_report"}:
            if str(arguments.get("change_id") or "").strip().upper() != str(
                workflow_state.get("change_id") or ""
            ).strip().upper():
                raise RuntimeError("Workflow의 change_id와 요청이 일치하지 않습니다.")
        if tool_name in {"run_ai_bom_review", "apply_reviewed_bom"}:
            if str(arguments.get("review_id") or "").strip().upper() != str(
                workflow_state.get("review_id") or ""
            ).strip().upper():
                raise RuntimeError("Workflow의 review_id와 요청이 일치하지 않습니다.")

    @staticmethod
    def _build_ai_workflow_state(
        tool_name: str,
        workflow_state: DesignChangeWorkflowState | None,
        arguments: dict[str, Any],
        tool_result: Any,
    ) -> DesignChangeWorkflowState:
        if not isinstance(tool_result, dict) or not tool_result.get("success"):
            raise RuntimeError(f"{tool_name} 실행에 실패했습니다: {tool_result}")
        updated = dict(workflow_state or create_initial_design_change_state())
        if tool_result.get("production_bom_modified") is True and tool_name != "apply_reviewed_bom":
            raise RuntimeError("최종 적용 전 단계에서 Production E-BOM을 변경할 수 없습니다.")
        if tool_name == "create_ai_change_request":
            analysis = tool_result.get("analysis", {})
            updated.update({
                "product_id": arguments.get("product_id"),
                "old_material_id": arguments.get("old_material_id"),
                "new_material_id": arguments.get("new_material_id"),
                "as_of_date": arguments.get("as_of_date"),
                "analysis_status": analysis.get("result", "PASS"),
                "analysis_result": analysis,
                "change_id": tool_result.get("change_id"),
                "current_step": "CHANGE_REQUESTED",
            })
        elif tool_name == "create_review_bom":
            updated.update({
                "review_id": tool_result.get("review_id"),
                "preview_status": "COMPLETED",
                "review_status": "WAITING",
                "current_step": "REVIEW_BOM_CREATED",
            })
        elif tool_name == "run_ai_bom_review":
            result = str(tool_result.get("workflow_result", "REVIEW_FAILED")).upper()
            updated.update({
                "ai_review_status": tool_result.get("ai_review_result", "FAIL"),
                "review_result": tool_result,
                "current_step": result,
            })
        elif tool_name == "generate_design_change_report":
            updated.update({
                "report_status": "COMPLETED",
                "report_result": tool_result,
                "current_step": "WAITING_FINAL_APPLY",
            })
        elif tool_name == "apply_reviewed_bom":
            if tool_result.get("production_bom_modified") is not True:
                raise RuntimeError("Production E-BOM 적용 확인에 실패했습니다.")
            updated.update({
                "apply_status": "COMPLETED",
                "apply_result": tool_result,
                "current_step": "CHANGE_COMPLETED",
            })
        return updated

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
