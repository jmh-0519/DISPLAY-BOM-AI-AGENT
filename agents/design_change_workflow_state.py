from typing import Literal, TypedDict


AnalysisStatus = Literal[
    "NOT_STARTED",
    "PASS",
    "CONDITIONAL",
    "FAIL",
]

WorkflowStatus = Literal[
    "NOT_STARTED",
    "WAITING",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
    "FAILED",
    "CONDITIONAL",
]

DesignChangeStep = Literal[
    "NOT_STARTED",
    "ANALYSIS_READY",
    "ANALYSIS_REVALIDATED",
    "ANALYSIS_IMPACT_REVIEW",
    "ANALYSIS_CONFIRMED",
    "ANALYSIS_COMPLETED",
    "ANALYSIS_BLOCKED",
    "WAITING_FINAL_APPROVAL",
    "REPORT_COMPLETED",
    "CANDIDATE_APPROVED",
    "PREVIEW_CREATED",
    "VALIDATED",
    "FINAL_APPROVED",
    "APPLIED",
    "BLOCKED",
]


class DesignChangeWorkflowState(TypedDict, total=False):
    """설계변경 Workflow의 업무 상태입니다."""

    product_id: str | None
    plant_code: str | None
    old_material_id: str | None
    new_material_id: str | None
    as_of_date: str | None
    analysis_status: AnalysisStatus
    analysis_result: dict | None
    preview_status: WorkflowStatus
    preview_revision: str | None
    preview_result: dict | None
    approval_status: WorkflowStatus
    approval_decision: Literal["APPROVE", "REJECT"] | None
    approval_comment: str | None
    approval_result: dict | None
    approved_preview_revision: str | None
    apply_status: WorkflowStatus
    apply_result: dict | None
    application_id: str | None
    report_status: WorkflowStatus
    report_result: dict | None
    current_step: DesignChangeStep
    request_id: str | None
    analysis_id: str | None
    analysis_request: dict | None
    analysis_base_request: dict | None
    analysis_initial_candidates: list[dict]
    analysis_initial_context: dict | None
    revalidation_history: list[dict]
    analysis_selection: list[dict]
    analysis_exception_reason: str | None
    analysis_impact_confirmed: bool
    actions: list[dict]
    candidates: list[dict]
    analysis_context: dict | None
    analysis_memory: dict | None
    last_explanation: dict | None
    last_followup_tool: str | None
    candidate_selection: list[dict]
    impact_review: dict | None
    candidate_approval_id: str | None
    final_approval_id: str | None
    impacts: list[dict]
    requires_exception: bool
    pending_quantity_request: str | None
    pending_add_target_request: dict | None
    pending_version_request: str | None


def create_initial_design_change_state() -> DesignChangeWorkflowState:
    """아직 시작되지 않은 설계변경 Workflow 상태를 생성합니다."""

    return {
        "product_id": None,
        "plant_code": None,
        "old_material_id": None,
        "new_material_id": None,
        "as_of_date": None,
        "analysis_status": "NOT_STARTED",
        "analysis_result": None,
        "preview_status": "NOT_STARTED",
        "preview_revision": None,
        "preview_result": None,
        "approval_status": "NOT_STARTED",
        "approval_decision": None,
        "approval_comment": None,
        "approval_result": None,
        "approved_preview_revision": None,
        "apply_status": "NOT_STARTED",
        "apply_result": None,
        "application_id": None,
        "report_status": "NOT_STARTED",
        "report_result": None,
        "current_step": "NOT_STARTED",
        "request_id": None,
        "analysis_id": None,
        "analysis_request": None,
        "analysis_base_request": None,
        "analysis_initial_candidates": [],
        "analysis_initial_context": None,
        "revalidation_history": [],
        "analysis_selection": [],
        "analysis_exception_reason": None,
        "analysis_impact_confirmed": False,
        "actions": [],
        "candidates": [],
        "analysis_context": None,
        "analysis_memory": None,
        "last_explanation": None,
        "last_followup_tool": None,
        "candidate_selection": [],
        "impact_review": None,
        "candidate_approval_id": None,
        "final_approval_id": None,
        "impacts": [],
        "requires_exception": False,
        "pending_quantity_request": None,
        "pending_add_target_request": None,
        "pending_version_request": None,
    }


def apply_design_change_tool_result(
    tool_name: str,
    workflow_state: DesignChangeWorkflowState | None,
    tool_result: dict,
) -> DesignChangeWorkflowState:
    """Design Change MCP Tool 결과를 Agent/UI 공통 Workflow 상태로 변환합니다."""

    if not isinstance(tool_result, dict):
        raise RuntimeError(f"{tool_name} result must be an object")

    updated = dict(
        workflow_state
        or create_initial_design_change_state()
    )

    if tool_name == "analyze_design_change_candidates":
        candidates = tool_result.get("candidates", [])
        counts = tool_result.get("status_counts") or {
            status: sum(value.get("status") == status for value in candidates)
            for status in ("PASS", "CONDITIONAL", "FAIL")
        }
        updated.update({
            "analysis_id": tool_result.get("analysis_id"),
            "analysis_request": tool_result.get("request"),
            "analysis_base_request": dict(tool_result.get("request") or {}),
            "request_id": None,
            "plant_code": (tool_result.get("request") or {}).get("plant_code"),
            "actions": tool_result.get("actions", []),
            "candidates": candidates,
            "analysis_initial_candidates": [dict(value) for value in candidates],
            "analysis_initial_context": dict(tool_result.get("analysis_context") or {}),
            "revalidation_history": [],
            "analysis_context": tool_result.get("analysis_context"),
            "analysis_memory": {
                "analysis_id": tool_result.get("analysis_id"),
                "candidate_count": len(candidates),
                "status_counts": counts,
                "request_created": False,
            },
            "analysis_selection": [],
            "analysis_exception_reason": None,
            "impact_review": None,
            "analysis_impact_confirmed": False,
            "candidate_selection": [],
            "candidate_approval_id": None,
            "final_approval_id": None,
            "current_step": "ANALYSIS_READY",
        })
    elif tool_name == "revalidate_design_change_analysis":
        candidates = tool_result.get("candidates", [])
        history = list(updated.get("revalidation_history", []))
        if tool_result.get("revalidation"):
            history.append(tool_result["revalidation"])
        updated.update({
            "analysis_request": tool_result.get("request") or updated.get("analysis_request"),
            "actions": tool_result.get("actions", updated.get("actions", [])),
            "candidates": candidates,
            "revalidation_history": history,
            "analysis_context": tool_result.get("analysis_context") or updated.get("analysis_context"),
            "analysis_memory": {
                "analysis_id": updated.get("analysis_id"),
                "candidate_count": len(candidates),
                "status_counts": tool_result.get("status_counts", {}),
                "request_created": False,
            },
            "current_step": "ANALYSIS_REVALIDATED",
        })
    elif tool_name == "preview_design_change_analysis_impact":
        updated.update({
            "impact_review": tool_result,
            "current_step": "ANALYSIS_IMPACT_REVIEW" if tool_result.get("requires_impact_approval") else "ANALYSIS_CONFIRMED",
        })
    elif tool_name == "create_design_change_request_from_analysis":
        updated.update({
            "request_id": tool_result.get("request_id"),
            "actions": tool_result.get("actions", []),
            "candidate_selection": tool_result.get("selections", []),
            "candidate_approval_id": tool_result.get("approval_id"),
            "requires_exception": False,
            "current_step": "CANDIDATE_APPROVED",
        })
    elif tool_name in {
        "explain_design_change_analysis_session",
        "explain_design_change_analysis_candidate",
        "compare_design_change_analysis_candidates",
        "get_design_change_analysis",
        "get_candidate_evaluation_detail",
        "compare_design_change_candidates",
    }:
        updated.update({
            "last_explanation": tool_result,
            "last_followup_tool": tool_name,
        })
    elif tool_name == "create_design_change_preview":
        status = tool_result.get("validation_status")
        updated.update({
            "preview_revision": tool_result.get("preview_id"),
            "impacts": tool_result.get("impacts", []),
            "current_step": (
                "BLOCKED"
                if status == "FAIL"
                else "WAITING_FINAL_APPROVAL"
            ),
        })
    elif tool_name == "record_final_apply_approval":
        updated.update({
            "final_approval_id": tool_result.get("approval_id"),
            "current_step": "FINAL_APPROVED",
        })
    elif tool_name == "apply_approved_change_request":
        updated.update({
            "application_id": tool_result.get("apply_id"),
            "apply_result": tool_result,
            "current_step": "APPLIED",
        })
    elif tool_name == "export_design_change_completion_report":
        updated.update({
            "report_status": "COMPLETED",
            "report_result": {
                "success": bool(tool_result.get("success")),
                "file_name": tool_result.get("file_name"),
            },
            "current_step": "REPORT_COMPLETED",
        })

    return updated
