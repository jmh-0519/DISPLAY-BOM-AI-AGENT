from core.database_config import sqlite_database_path
from database import SQLiteDatabase
from services.design_change_workflow_service import DesignChangeWorkflowService
from core.performance_profiler import performance_span


def _service() -> DesignChangeWorkflowService:
    return DesignChangeWorkflowService(SQLiteDatabase(sqlite_database_path()))


def create_design_change_request_data(request: dict, actions: list[dict]) -> dict:
    return _service().create_request(request, actions)


def evaluate_replacement_candidates_data(action_id: str) -> dict:
    return _service().evaluate_action(action_id)


def select_candidate_and_supplier_data(request_id: str, selections: list[dict],
                                       approved_by: str) -> dict:
    # STEP29: selection may stop at shared-BOM impact review before Workflow starts.
    return _service().prepare_candidate_selection(request_id, selections, approved_by)




def confirm_candidate_selection_data(
    request_id: str, selections: list[dict], confirmed_by: str,
    exception_reason: str | None = None,
) -> dict:
    return _service().confirm_candidate_selection(
        request_id=request_id, selections=selections, confirmed_by=confirmed_by,
        exception_reason=exception_reason,
    )

def approve_candidate_impact_data(request_id: str, approved_by: str) -> dict:
    return _service().approve_candidate_impact(request_id, approved_by)


def submit_candidate_additional_data_data(
    action_id: str, candidate_item_code: str, attributes: dict | None = None,
    demand_quantity: float | None = None,
) -> dict:
    return _service().submit_additional_data(
        action_id=action_id, candidate_item_code=candidate_item_code,
        attributes=attributes, demand_quantity=demand_quantity,
    )


def record_exception_approval_data(request_id: str, reason: str, approved_by: str) -> dict:
    return _service().approve_exception(request_id, reason, approved_by)


def create_multi_action_preview_data(request_id: str, created_by: str) -> dict:
    return _service().create_preview(request_id, created_by)


def record_final_apply_approval_data(request_id: str, approved_by: str) -> dict:
    return _service().approve_final(request_id, approved_by)


def apply_approved_change_request_data(request_id: str, final_approval_id: str,
                                       applied_by: str) -> dict:
    return _service().apply(request_id, final_approval_id, applied_by)


def get_change_request_result_data(request_id: str) -> dict:
    return _service().get_result(request_id)


def get_design_change_analysis_data(request_id: str) -> dict:
    return _service().get_analysis_explanation(request_id)


def get_candidate_evaluation_detail_data(
    request_id: str,
    candidate_item_code: str,
    action_id: str | None = None,
) -> dict:
    return _service().get_candidate_evaluation_detail(
        request_id=request_id,
        candidate_item_code=candidate_item_code,
        action_id=action_id,
    )


def compare_design_change_candidates_data(
    request_id: str,
    candidate_item_codes: list[str] | None = None,
    action_id: str | None = None,
    criterion: str = "SPEC_SIMILARITY",
) -> dict:
    return _service().compare_candidates(
        request_id=request_id,
        candidate_item_codes=candidate_item_codes,
        action_id=action_id,
        criterion=criterion,
    )


def analyze_design_change_candidates_data(request: dict, actions: list[dict]) -> dict:
    with performance_span(
        "service",
        "design_change.analyze_design_change_candidates",
        metadata={
            "action_count": len(actions or []),
            "plant_present": bool((request or {}).get("plant_code")),
            "version_present": bool((request or {}).get("version_code")),
        },
    ):
        return _service().analyze_candidates(request, actions)


def scan_product_cost_reduction_candidates_data(
    version_code: str,
    plant_code: str,
    as_of_date: str | None = None,
    exclude_item_codes: list[str] | None = None,
    exclude_item_names: list[str] | None = None,
    include_target_types: list[str] | None = None,
    candidates_per_item: int = 5,
) -> dict:
    return _service().scan_product_cost_reduction_candidates(
        version_code=version_code,
        plant_code=plant_code,
        as_of_date=as_of_date,
        exclude_item_codes=exclude_item_codes,
        exclude_item_names=exclude_item_names,
        include_target_types=include_target_types,
        candidates_per_item=candidates_per_item,
    )


def revalidate_design_change_analysis_data(
    analysis: dict, action_id: str, candidate_item_code: str,
    demand_quantity: float | None = None, attributes: dict | None = None,
) -> dict:
    return _service().revalidate_analysis_candidate(
        analysis=analysis, action_id=action_id, candidate_item_code=candidate_item_code,
        demand_quantity=demand_quantity, attributes=attributes,
    )


def preview_design_change_analysis_impact_data(analysis: dict, selections: list[dict]) -> dict:
    return _service().preview_analysis_impact(analysis, selections)


def create_design_change_request_from_analysis_data(
    analysis: dict, selections: list[dict], approved_by: str,
    exception_reason: str | None = None, impact_confirmed: bool = False,
) -> dict:
    return _service().commit_analysis_as_request(
        analysis=analysis, selections=selections, approved_by=approved_by,
        exception_reason=exception_reason, impact_confirmed=impact_confirmed,
    )


def explain_design_change_analysis_session_data(analysis: dict) -> dict:
    return _service().explain_analysis_session(analysis)


def explain_design_change_analysis_candidate_data(analysis: dict, candidate_item_code: str, action_id: str | None = None) -> dict:
    return _service().explain_analysis_candidate(analysis, candidate_item_code, action_id)


def compare_design_change_analysis_candidates_data(analysis: dict, candidate_item_codes: list[str] | None = None, action_id: str | None = None, criterion: str = "SPEC_SIMILARITY") -> dict:
    return _service().compare_analysis_candidates(analysis, candidate_item_codes, action_id, criterion)
