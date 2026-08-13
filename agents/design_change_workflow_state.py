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
    "ANALYSIS_COMPLETED",
    "ANALYSIS_BLOCKED",
    "WAITING_PREVIEW",
    "WAITING_REVIEW",
    "REVIEW_CONDITIONAL",
    "REVIEW_REJECTED",
    "WAITING_FINAL_APPROVAL",
    "READY_TO_APPLY",
    "CHANGE_REJECTED",
    "APPLY_COMPLETED",
    "REPORT_COMPLETED",
    "CHANGE_REQUESTED",
    "REVIEW_BOM_CREATED",
    "AI_REVIEW_COMPLETED",
    "REVIEW_NEEDS_CONFIRMATION",
    "REVIEW_FAILED",
    "WAITING_FINAL_APPLY",
    "CHANGE_COMPLETED",
]


class DesignChangeWorkflowState(TypedDict, total=False):
    """설계변경 Workflow의 업무 상태입니다."""

    product_id: str | None
    old_material_id: str | None
    new_material_id: str | None
    as_of_date: str | None
    analysis_status: AnalysisStatus
    analysis_result: dict | None
    preview_status: WorkflowStatus
    preview_revision: str | None
    preview_result: dict | None
    review_status: WorkflowStatus
    review_result: dict | None
    reviewed_preview_revision: str | None
    approval_status: WorkflowStatus
    approval_decision: Literal["APPROVE", "REJECT"] | None
    approval_comment: str | None
    approval_result: dict | None
    approved_preview_revision: str | None
    apply_status: WorkflowStatus
    apply_result: dict | None
    application_id: str | None
    report_status: WorkflowStatus
    change_id: str | None
    review_id: str | None
    ai_review_status: WorkflowStatus
    report_result: dict | None
    current_step: DesignChangeStep


def create_initial_design_change_state() -> DesignChangeWorkflowState:
    """아직 시작되지 않은 설계변경 Workflow 상태를 생성합니다."""

    return {
        "product_id": None,
        "old_material_id": None,
        "new_material_id": None,
        "as_of_date": None,
        "analysis_status": "NOT_STARTED",
        "analysis_result": None,
        "preview_status": "NOT_STARTED",
        "preview_revision": None,
        "preview_result": None,
        "review_status": "NOT_STARTED",
        "review_result": None,
        "reviewed_preview_revision": None,
        "approval_status": "NOT_STARTED",
        "approval_decision": None,
        "approval_comment": None,
        "approval_result": None,
        "approved_preview_revision": None,
        "apply_status": "NOT_STARTED",
        "apply_result": None,
        "application_id": None,
        "report_status": "NOT_STARTED",
        "change_id": None,
        "review_id": None,
        "ai_review_status": "NOT_STARTED",
        "report_result": None,
        "current_step": "NOT_STARTED",
    }
