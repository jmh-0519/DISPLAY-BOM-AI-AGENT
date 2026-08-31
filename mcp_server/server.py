from pathlib import Path
import sys

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from mcp.server import MCPServer

from mcp_server.capabilities.query import (
    get_bom_data,
    list_plants_data,
    list_materials_data,
    list_products_data,
    search_material_data,
    search_product_data,
    get_where_used_data,
    get_product_detail_data,
    get_item_detail_data,
)
from mcp_server.capabilities.download import (
    export_bom_excel_data,
    export_design_change_completion_report_data,
)
from mcp_server.capabilities.design_change_workflow import (
    apply_approved_change_request_data,
    analyze_design_change_candidates_data,
    scan_product_cost_reduction_candidates_data,
    revalidate_design_change_analysis_data,
    preview_design_change_analysis_impact_data,
    create_design_change_request_from_analysis_data,
    explain_design_change_analysis_session_data,
    explain_design_change_analysis_candidate_data,
    compare_design_change_analysis_candidates_data,
    create_design_change_preview_data,
    get_change_request_result_data,
    get_design_change_analysis_data,
    get_candidate_evaluation_detail_data,
    compare_design_change_candidates_data,
    record_final_apply_approval_data,
)
from mcp_server.capabilities.management import (
    create_rule_data, deactivate_rule_data, export_training_dataset_data,
    list_design_change_history_data, list_rules_data,
    record_performance_outcome_data, update_rule_data,
)
from mcp_server.schemas import (
    DesignChangeActionInput,
    DesignChangeRequestInput,
)

mcp = MCPServer(
    "Display BOM MCP Server"
)

@mcp.tool()
def get_bom(
    plant_code: str,
    product_id: str,
    as_of_date: str | None = None,
) -> list[dict]:
    """
    Plant, 제품 ID와 기준일을 이용하여
    계층형 BOM 데이터를 조회합니다.

    Args:
        plant_code:
            조회할 Plant 코드. 예: P01

        product_id:
            조회할 제품 ID

        as_of_date:
            BOM 기준일.
            예: 2026-08-11

    Returns:
        BOM Row 목록
    """

    return get_bom_data(
        plant_code=plant_code,
        product_id=product_id,
        as_of_date=as_of_date,
    )

@mcp.tool()
def get_bom_where_used(
    item_code: str,
    plant_code: str,
    as_of_date: str | None = None,
) -> dict:
    """
    자재/ASSY가 선택한 PLANT의 어떤 상위 ASSY와 최상위 MODEL에
    사용되는지 역방향 BOM으로 조회합니다.
    """
    return get_where_used_data(
        item_code=item_code, plant_code=plant_code, as_of_date=as_of_date
    )

@mcp.tool()
def get_product_detail(
    product_id: str,
    as_of_date: str | None = None,
) -> dict:
    """모델 코드의 Master 및 상세 속성정보를 조회합니다."""
    return get_product_detail_data(product_id, as_of_date)

@mcp.tool()
def get_item_detail(
    item_code: str,
    as_of_date: str | None = None,
) -> dict:
    """MATERIAL/ASSY 코드의 Master 및 상세 속성정보를 조회합니다."""
    return get_item_detail_data(item_code, as_of_date)

@mcp.tool()
def list_products() -> list[dict]:
    """
    등록된 전체 제품 목록을 조회합니다.
    """

    return list_products_data()

@mcp.tool()
def search_product(
    keyword: str,
) -> list[dict]:
    """
    제품 ID 또는 제품명에 포함된
    키워드로 제품을 검색합니다.
    """

    return search_product_data(
        keyword
    )

@mcp.tool()
def list_materials() -> list[dict]:
    """
    등록된 전체 자재 목록을 조회합니다.
    """

    return list_materials_data()

@mcp.tool()
def search_material(
    keyword: str,
) -> list[dict]:
    """
    자재 ID 또는 자재명에 포함된
    키워드로 자재를 검색합니다.
    """

    return search_material_data(
        keyword
    )

@mcp.tool()
def list_plants(
    reference_code: str | None = None,
    as_of_date: str | None = None,
) -> list[dict]:
    """BOM 조회/설계변경 대상이 실제 존재하는 활성 Plant를 조회합니다.

    reference_code가 VERSION/ASSY/MATERIAL이면 해당 품목이 활성 BOM에 존재하는
    Plant만 반환합니다. 대상이 없을 때만 전체 활성 Plant 조회가 가능합니다.
    """
    return list_plants_data(reference_code, as_of_date)

@mcp.tool()
def export_bom_excel(plant_code: str, product_id: str, as_of_date: str | None = None) -> dict:
    """BOM 조회 결과를 읽기 전용 Excel 파일로 생성합니다."""
    return export_bom_excel_data(
        plant_code=plant_code, product_id=product_id, as_of_date=as_of_date
    )

@mcp.tool()
def export_design_change_completion_report(request_id: str) -> dict:
    """Apply가 완료된 Design Change Request의 설계변경 완료 Word 보고서를 생성합니다."""
    return export_design_change_completion_report_data(request_id=request_id)

@mcp.tool()
def analyze_design_change_candidates(
    request: DesignChangeRequestInput,
    actions: list[DesignChangeActionInput],
) -> dict:
    """단일 Action 설계변경 후보를 분석합니다.

    actions에는 정확히 하나의 업무 Action만 전달해야 합니다. 동일 Action이 사유별로
    중복 생성된 경우 Service가 하나로 병합하지만 서로 다른 복수 Action은 거부합니다.
    이 Tool은 Analysis Session만 생성하며 change_requests/change_actions를 만들지 않습니다.
    후보 탐색, 복수 Reason 평가, 공급사/재고 평가까지만 수행합니다.
    REPLACE뿐 아니라 ADD/DELETE/QUANTITY_CHANGE를 지원합니다. ADD는 new_item_code를
    모르는 경우에도 target_type과 Reason/Rule을 기준으로 후보 전체를 탐색할 수 있습니다.
    DELETE는 후보 없이 영향분석으로 진행하고, QUANTITY_CHANGE는 변경 후 BOM 소요량 기준
    재고를 검증합니다. REPLACE/DELETE/QUANTITY_CHANGE에서 old_item_code를 모르는 경우
    target_item_name만 전달하면 지정된 VERSION/PLANT 활성 BOM 안에서 source item을
    resolve한 뒤 같은 Tool 호출에서 분석까지 계속합니다.
    """
    return analyze_design_change_candidates_data(request, actions)

@mcp.tool()
def scan_product_cost_reduction_candidates(
    version_code: str,
    plant_code: str,
    as_of_date: str | None = None,
    exclude_item_codes: list[str] | None = None,
    exclude_item_names: list[str] | None = None,
    include_target_types: list[str] | None = None,
    candidates_per_item: int = 5,
) -> dict:
    """제품 BOM 전체를 읽기 전용으로 순회해 원가절감 대체 후보 기회를 탐색합니다.

    특정 단일 품목 설계변경 Analysis가 아니라 제품 단위 Opportunity Scan입니다.
    실제 Design Change Request나 Production BOM은 생성/변경하지 않습니다.
    원가 절감은 현재품과 후보의 비교 가능한 단가 근거가 모두 있을 때만 확정합니다.
    """
    return scan_product_cost_reduction_candidates_data(
        version_code=version_code,
        plant_code=plant_code,
        as_of_date=as_of_date,
        exclude_item_codes=exclude_item_codes,
        exclude_item_names=exclude_item_names,
        include_target_types=include_target_types,
        candidates_per_item=candidates_per_item,
    )

@mcp.tool()
def revalidate_design_change_analysis(
    analysis: dict, action_id: str, candidate_item_code: str,
    attributes: dict | None = None,
) -> dict:
    """Analysis Session의 추가정보를 반영해 재검증합니다. 실제 Request나 BOM은 변경하지 않습니다."""
    return revalidate_design_change_analysis_data(
        analysis, action_id, candidate_item_code, attributes
    )

@mcp.tool()
def preview_design_change_analysis_impact(analysis: dict, selections: list[dict]) -> dict:
    """선택 후보의 공용 BOM 영향과 Before/After Spec을 Request 생성 전에 읽기 전용으로 분석합니다."""
    return preview_design_change_analysis_impact_data(analysis, selections)

@mcp.tool()
def create_design_change_request_from_analysis(
    analysis: dict, selections: list[dict], approved_by: str,
    exception_reason: str | None = None, impact_confirmed: bool = False,
) -> dict:
    """사용자가 분석안을 확인하고 설계변경 진행을 명시적으로 승인한 경우에만 실제 Request를 생성합니다."""
    return create_design_change_request_from_analysis_data(
        analysis, selections, approved_by, exception_reason, impact_confirmed
    )

@mcp.tool()
def explain_design_change_analysis_session(analysis: dict) -> dict:
    """Request 생성 전 Analysis Session의 후보 수와 PASS/CONDITIONAL/FAIL 근거를 설명합니다."""
    return explain_design_change_analysis_session_data(analysis)

@mcp.tool()
def explain_design_change_analysis_candidate(analysis: dict, candidate_item_code: str, action_id: str | None = None) -> dict:
    """Request 생성 전 특정 후보의 Rule/Spec/재고/공급사 근거를 설명합니다."""
    return explain_design_change_analysis_candidate_data(analysis, candidate_item_code, action_id)

@mcp.tool()
def compare_design_change_analysis_candidates(analysis: dict, candidate_item_codes: list[str] | None = None, action_id: str | None = None, criterion: str = "SPEC_SIMILARITY") -> dict:
    """Request 생성 전 Analysis Session 후보를 비교합니다."""
    return compare_design_change_analysis_candidates_data(analysis, candidate_item_codes, action_id, criterion)

@mcp.tool()
def create_design_change_preview(request_id: str, created_by: str) -> dict:
    """승인 후보와 전체 공용 ASSY 영향을 포함한 최종 Preview를 생성합니다."""
    return create_design_change_preview_data(request_id, created_by)

@mcp.tool()
def record_final_apply_approval(request_id: str, approved_by: str) -> dict:
    """최종 Preview에 대한 2차 Apply 승인을 기록합니다."""
    return record_final_apply_approval_data(request_id, approved_by)

@mcp.tool()
def apply_approved_change_request(request_id: str, final_approval_id: str,
                                  applied_by: str) -> dict:
    """두 승인과 Preview가 유효한 요청의 모든 Action을 한 Transaction으로 적용합니다."""
    return apply_approved_change_request_data(request_id, final_approval_id, applied_by)

@mcp.tool()
def get_change_request_result(request_id: str) -> dict:
    """설계변경 요청과 Action 상태를 읽기 전용으로 조회합니다."""
    return get_change_request_result_data(request_id)

@mcp.tool()
def get_design_change_analysis(request_id: str) -> dict:
    """현재 설계변경 후보 분석의 상태와 실패/조건부 근거를 읽기 전용으로 요약합니다.

    후보가 아예 없는 상태와 후보는 검색됐지만 모두 FAIL인 상태를 구분합니다.
    이전 분석을 다시 실행하거나 후보 상태를 변경하지 않습니다.
    """
    return get_design_change_analysis_data(request_id)

@mcp.tool()
def get_candidate_evaluation_detail(
    request_id: str,
    candidate_item_code: str,
    action_id: str | None = None,
) -> dict:
    """특정 후보의 기술/Spec, Rule, 재고, 공급사 평가 근거를 읽기 전용으로 조회합니다.

    FAIL/CONDITIONAL 사유를 설명할 때 사용하며 결과를 재판정하지 않습니다.
    """
    return get_candidate_evaluation_detail_data(
        request_id, candidate_item_code, action_id
    )

@mcp.tool()
def compare_design_change_candidates(
    request_id: str,
    candidate_item_codes: list[str] | None = None,
    action_id: str | None = None,
    criterion: str = "SPEC_SIMILARITY",
) -> dict:
    """현재 분석 후보를 Spec 유사도, 점수, 원가, 납기 또는 재고 기준으로 비교합니다.

    criterion은 SPEC_SIMILARITY, TOTAL_SCORE, COST, LEAD_TIME, INVENTORY 중 하나입니다.
    FAIL 후보가 비교 1위여도 승인 가능한 후보라는 의미는 아닙니다.
    """
    return compare_design_change_candidates_data(
        request_id, candidate_item_codes, action_id, criterion
    )

@mcp.tool()
def list_rules(as_of_date: str | None = None) -> list[dict]:
    return list_rules_data(as_of_date)

@mcp.tool()
def create_rule(rule: dict, conditions: list[dict]) -> dict:
    return create_rule_data(rule, conditions)

@mcp.tool()
def update_rule(rule: dict, conditions: list[dict]) -> dict:
    return update_rule_data(rule, conditions)

@mcp.tool()
def deactivate_rule(rule_id: str, revision_no: int) -> dict:
    return deactivate_rule_data(rule_id, revision_no)

@mcp.tool()
def list_design_change_history() -> list[dict]:
    return list_design_change_history_data()

@mcp.tool()
def record_performance_outcome(request_id: str, measurement_day: int,
                               outcome: dict, measured_at: str,
                               user_rating: int | None = None) -> dict:
    return record_performance_outcome_data(
        request_id, measurement_day, outcome, user_rating, measured_at,
    )

@mcp.tool()
def export_training_dataset(date_from: str | None = None,
                            date_to: str | None = None,
                            created_by: str = "system") -> dict:
    return export_training_dataset_data(date_from, date_to, created_by)

if __name__ == "__main__":
    mcp.run()
